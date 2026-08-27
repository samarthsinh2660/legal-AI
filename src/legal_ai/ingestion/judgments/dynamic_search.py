"""Lazy-cached dynamic judgment search — the fetch + verify step only.

See docs/superpowers/specs/2026-08-17-dynamic-judgment-search-design.md.
Finds a judgment and runs it through the Source Verification Gate.
Storing it is a separate step (see judgments/store.py); nothing here
writes to Postgres or Neo4j.

Flow per lookup:
1. Check the DB (title word-overlap over document_type='judgment', not
   embedding similarity -- documents are embedded on full_text, so a short
   case-name query sits far from even the correct match).
2. Bharat Courts' ArchiveClient -- the public Vanga AWS Open Data archive
   covering the Supreme Court and any state High Court, no CAPTCHA.
3. Indian Kanoon -- public aggregator, last resort, labelled as such.
4. verify_batch -- the same gate as India Code, no lighter bar.

Note: ArchiveClient.fetch_pdf caches a whole year's PDF bundle (hundreds
of MB) locally on first use for a year/court. That is the SDK's own
caching, not controlled here.
"""

from __future__ import annotations

import asyncio
import io
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal, Optional

import pypdf
from bs4 import BeautifulSoup

from legal_ai.ingestion.schema import CanonicalDocument, content_hash
from legal_ai.ingestion.verification_gate import verify_batch
from legal_ai.knowledge.static.db import get_connection
from legal_ai.knowledge.static.store import get_document
from legal_ai.schemas.evidence import Provenance, SourceRef
from legal_ai.sources.http import polite_get
from legal_ai.sources.robots import is_allowed

_WORD_RE = re.compile(r"[a-zA-Z]{3,}")

# Fraction of the query's significant (3+ letter) words that must appear
# in a candidate judgment's title, case-insensitively, to treat it as
# the same case rather than merely a related one.
DB_TITLE_WORD_OVERLAP_THRESHOLD = 0.6

IK_SEARCH_URL = "https://indiankanoon.org/search/"
IK_DOC_ID_RE = re.compile(r"/doc(?:fragment)?/(\d+)/")

SourceName = Literal["database", "bharat_courts_archive", "indian_kanoon", "none"]


@dataclass
class JudgmentSearchResult:
    found: bool
    source: SourceName
    documents: list[CanonicalDocument] = field(default_factory=list)
    verified: Optional[bool] = None
    notes: list[str] = field(default_factory=list)

    @property
    def document(self) -> Optional[CanonicalDocument]:
        """The best match. Kept so a caller wanting one judgment -- a
        lookup by case name -- does not have to index into a list."""
        return self.documents[0] if self.documents else None


# Fraction of a judgment's characters that must be letters for the text to
# be prose rather than noise. Measured over 4,070 judgments on 2026-08-27:
# real text clusters at 0.6-0.8, while PDFs with a broken font encoding map
# extract as mojibake (`!" #$%$ &'())`) at 0.03-0.06. At 0.15 the split is
# clean -- 174 rejected, none of them readable, and the shortest genuine
# procedural orders (alpha 0.22) survive.
MIN_ALPHA_RATIO = 0.15


def _text_check(doc: CanonicalDocument) -> bool:
    """Length alone was not enough.

    A scanned judgment whose text layer holds only the registrar's
    e-signature ("I attest to the accuracy and integrity of this document")
    clears 200 characters, and so does a whole document of mojibake -- one
    was 60,857 characters of it. Both were being embedded, chunked and made
    retrievable as though they were judgments.
    """
    text = doc.full_text.strip()
    if len(text) < 200:
        return False
    letters = sum(1 for ch in text if ch.isalpha())
    return letters / len(text) >= MIN_ALPHA_RATIO


def _verify(documents: list[CanonicalDocument]) -> tuple[bool, list[str]]:
    result = verify_batch(documents, text_check=_text_check)
    return result.passed, result.notes


def _check_db(query: str, limit: int = 1) -> list[CanonicalDocument]:
    """Stored judgments whose titles share enough words with `query`.

    Overlap is computed in SQL. Doing it in Python meant selecting every
    judgment id and then re-reading each row in full -- pulling the entire
    judgment corpus, full text and all, over the wire to compare titles.
    That is invisible at nine stored judgments and impossible at fifty
    thousand, which is where a real precedent corpus lands.
    """
    query_words = sorted({w.lower() for w in _WORD_RE.findall(query)})
    if not query_words:
        return []

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT document_id FROM (
                    SELECT document_id,
                           cardinality(ARRAY(
                               SELECT unnest(%s::text[])
                               INTERSECT
                               SELECT unnest(regexp_split_to_array(lower(title), '[^a-z]+'))
                           ))::float / %s AS overlap
                    FROM documents
                    WHERE document_type = 'judgment'
                ) scored
                WHERE overlap >= %s
                ORDER BY overlap DESC, document_id ASC
                LIMIT %s
                """,
                (query_words, len(query_words), DB_TITLE_WORD_OVERLAP_THRESHOLD, limit),
            )
            ids = [row[0] for row in cur.fetchall()]
        found = [doc for doc in (get_document(conn, i) for i in ids) if doc is not None]
    finally:
        conn.close()
    return found


def _archive_pdf_url(judgment) -> tuple[str, bool]:
    """Public HTTPS URL for a judgment's PDF, plus whether it is a
    single-document link (True) or a bundled archive containing it
    (False -- SCI ships one tar per year, with no per-document URL).
    """
    from bharat_courts.archive.endpoints import HC_PDF_HTTPS, SCI_TAR_HTTPS
    from bharat_courts.models import CourtType

    if judgment.court and judgment.court.court_type == CourtType.SUPREME_COURT:
        return SCI_TAR_HTTPS.format(year=judgment.year, lang_dir="english"), False

    court_partition = (judgment.court_code or "").replace("~", "_")
    basename = (judgment.pdf_path or "").rsplit("/", 1)[-1]
    return (
        HC_PDF_HTTPS.format(
            year=judgment.year, court_partition=court_partition, bench=judgment.bench, basename=basename
        ),
        True,
    )


def _strip_nuls(text: str) -> str:
    """PostgreSQL text columns cannot hold NUL (0x00), and pypdf emits them
    from some scanned PDFs' text layers.

    Measured 2026-08-27: one judgment in ~1,500 raised
    `DataError: PostgreSQL text fields cannot contain NUL (0x00) bytes`
    and was dropped as a counted skip -- a real judgment lost to a byte
    that carries no meaning. Stripped here, before content_hash is taken,
    so the hash describes what is actually stored.
    """
    return text.replace("\x00", "")


def _to_canonical(judgment, full_text: str, fallback_title: str) -> CanonicalDocument:
    full_text = _strip_nuls(full_text)
    document_id = f"judgment:{(judgment.cnr or judgment.case_id or content_hash(judgment.title or fallback_title)[:12]).lower()}"
    court_name = judgment.court.name if judgment.court else (judgment.court_name_raw or None)
    parties = None
    if judgment.petitioner or judgment.respondent:
        parties = {"petitioner": judgment.petitioner, "respondent": judgment.respondent}

    pdf_url, is_single_doc = _archive_pdf_url(judgment)
    source_name = "Bharat Courts archive (Vanga public AWS Open Data, direct PDF)"
    if not is_single_doc:
        source_name = (
            "Bharat Courts archive (Vanga public AWS Open Data — bundled year tar, "
            "not a single-document link; this judgment's PDF is one file inside it)"
        )

    return CanonicalDocument(
        document_id=document_id,
        document_type="judgment",
        title=_strip_nuls(judgment.title or fallback_title),
        court=court_name,
        citation=judgment.citation,
        case_number=judgment.case_id,
        parties=parties,
        decision_date=judgment.decision_date,
        disposal_nature=judgment.disposal_nature,
        full_text=full_text,
        content_hash=content_hash(full_text),
        provenance=Provenance(
            source=SourceRef(
                name=source_name,
                url=pdf_url,
                document_id=document_id,
                source_type="primary",
            ),
            retrieved_at=datetime.now(timezone.utc),
            licence="CC-BY-4.0 (Vanga public AWS Open Data archives)",
            attribution_required=True,
        ),
        ingested_at=datetime.now(timezone.utc),
    )


def _search_bharat_courts_archive(
    query: str, year: int | tuple[int, int] | None, limit: int = 1
) -> list[CanonicalDocument]:
    """Up to `limit` judgments from the public archive.

    Previously this searched three and kept one, which made the lazy cache
    grow by a single judgment per lookup no matter how many real matches
    the query had. A corpus that grows one document at a time never becomes
    able to answer a question by issue.

    One PDF that fails to parse is skipped, not fatal: a scanned judgment
    with no text layer must not cost the caller the others.
    """
    import bharat_courts as bc

    async def _search_and_fetch():
        async with bc.ArchiveClient() as client:
            results = await client.search(party=query, year=year, limit=limit)
            fetched = []
            for judgment in results:
                try:
                    fetched.append((judgment, await client.fetch_pdf(judgment)))
                except Exception:
                    continue
            return fetched

    documents: list[CanonicalDocument] = []
    for judgment, pdf_bytes in asyncio.run(_search_and_fetch()):
        try:
            reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
            full_text = "\n".join(page.extract_text() or "" for page in reader.pages)
        except Exception:
            continue
        if not full_text.strip():
            continue
        documents.append(_to_canonical(judgment, full_text, query))
    return documents


def _fetch_indian_kanoon_doc(doc_id: str, title: str) -> Optional[CanonicalDocument]:
    doc_url = f"https://indiankanoon.org/doc/{doc_id}/"

    # robots.txt names thousands of specific /doc/<id>/ paths as disallowed
    # -- judgments ordered de-indexed, typically victim-privacy matters.
    # Serving one of those to a user republishes what a court suppressed.
    if not is_allowed(doc_url):
        return None

    doc_response = polite_get(doc_url)
    if doc_response.status_code != 200:
        return None
    doc_soup = BeautifulSoup(doc_response.text, "html.parser")
    body = doc_soup.find(class_="judgments")
    if body is None:
        return None
    full_text = body.get_text(separator="\n", strip=True)
    if len(full_text.strip()) < 200:
        return None

    doc_title_el = doc_soup.find(class_="doc_title")
    if doc_title_el is not None:
        title = doc_title_el.get_text(strip=True)

    document_id = f"judgment:ik-{doc_id}"
    return CanonicalDocument(
        document_id=document_id,
        document_type="judgment",
        title=title,
        full_text=full_text,
        content_hash=content_hash(full_text),
        provenance=Provenance(
            source=SourceRef(
                name="Indian Kanoon (public case-law aggregator, not an official government source)",
                url=doc_url,
                document_id=document_id,
                source_type="research",
            ),
            retrieved_at=datetime.now(timezone.utc),
            licence="Public case-law aggregator — not an official government source",
            attribution_required=True,
        ),
        ingested_at=datetime.now(timezone.utc),
    )


def _search_indian_kanoon(
    query: str, limit: int = 1, court: str | None = None
) -> list[CanonicalDocument]:
    """Up to `limit` judgments from Indian Kanoon's full-text search.

    This is the only source here that can be searched by *issue* rather
    than by case name -- the archive index carries no subject, headnote or
    keyword column, so a query like "commercial quantity bail" has nothing
    to match there. That makes this path the one that can answer a question
    the user cannot already name a case for.

    Every document fetch is checked against robots.txt first. Taking more
    than one result multiplies how often a suppressed id would be
    requested, which is why the check is here and not left for later.
    """
    # `doctypes:` is the site's own court filter, and the only court filter
    # available on a search by issue -- the archive index has no subject
    # column to filter instead.
    form_input = f"{query} doctypes:{court}" if court else query
    response = polite_get(IK_SEARCH_URL, params={"formInput": form_input})
    if response.status_code != 200:
        return []
    soup = BeautifulSoup(response.text, "html.parser")

    documents: list[CanonicalDocument] = []
    seen: set[str] = set()
    for result_title in soup.find_all(class_="result_title"):
        if len(documents) >= limit:
            break
        link = result_title.find("a")
        if link is None or not link.get("href"):
            continue
        match = IK_DOC_ID_RE.search(link["href"])
        if match is None or match.group(1) in seen:
            continue
        seen.add(match.group(1))
        document = _fetch_indian_kanoon_doc(
            match.group(1), result_title.get_text(strip=True)
        )
        if document is not None:
            documents.append(document)
    return documents


def search_judgments(
    query: str,
    year: int | tuple[int, int] | None = None,
    limit: int = 1,
    skip_db: bool = False,
    live: bool = True,
) -> JudgmentSearchResult:
    """Find up to `limit` real judgments for `query`.

    `limit=1` is a lookup: the caller knows the case name or citation and
    wants that document. Above one it becomes discovery, and the source
    that matters changes -- the archive index has no subject column, so
    only the full-text path can answer a query phrased as an issue.

    `year` (single year or inclusive range) is strongly recommended for the
    archive: with no court specified it scans the Supreme Court plus all
    ~25 High Court partitions, and a year enables partition pruning.

    `skip_db`: the DB check matches on title word-overlap, which cannot
    distinguish two real proceedings between the same parties (a main
    judgment vs. a later review-petition order on the same appeal). Pass
    `skip_db=True` to force a fresh live search when a cached match is
    the wrong document.

    `live=False` searches the database only. The live path is slow by
    nature -- with no court given the archive scans every partition,
    measured at 228s for a query that found nothing -- so an interactive
    caller must not block on it. Fetching a judgment the corpus lacks is
    corpus growth, not query-time work.

    Does not store anything -- see the module docstring.
    """
    if not skip_db:
        stored = _check_db(query, limit=limit)
        if len(stored) >= limit:
            return JudgmentSearchResult(
                found=True,
                source="database",
                documents=stored,
                verified=True,
                notes=[f"{len(stored)} match(es) already in DB, no network call made"],
            )

    if not live:
        stored = stored if not skip_db else []
        if stored:
            return JudgmentSearchResult(
                found=True, source="database", documents=stored, verified=True,
                notes=[
                    f"{len(stored)} of {limit} requested found in DB; "
                    "live search was not attempted"
                ],
            )
        return JudgmentSearchResult(
            found=False,
            source="none",
            notes=[f"no stored judgment matches {query!r}; live search was not attempted"],
        )

    documents = _search_bharat_courts_archive(query, year, limit=limit)
    source: SourceName = "bharat_courts_archive"
    if not documents:
        documents = _search_indian_kanoon(query, limit=limit)
        source = "indian_kanoon"

    if not documents:
        notes = [f"no result for {query!r} in DB, Bharat Courts archive, or Indian Kanoon"]
        if year is None:
            notes.append("no year was given — pass one if known, it materially improves archive recall/speed")
        return JudgmentSearchResult(found=False, source="none", notes=notes)

    passed, notes = _verify(documents)
    if source == "bharat_courts_archive" and year is None:
        notes.append("found without a year filter — this query scanned every partition, consider passing year")
    return JudgmentSearchResult(
        found=True, source=source, documents=documents, verified=passed, notes=notes
    )


def search_judgment(
    query: str,
    year: int | tuple[int, int] | None = None,
    skip_db: bool = False,
    live: bool = True,
) -> JudgmentSearchResult:
    """One judgment for `query` -- lookup by case name or citation.

    Kept as the single-result entry point so callers that want exactly one
    document read as wanting one. See search_judgments for discovery.
    """
    return search_judgments(query, year=year, limit=1, skip_db=skip_db, live=live)
