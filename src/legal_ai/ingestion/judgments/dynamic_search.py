"""Lazy-cached dynamic judgment search — the fetch + verify step only.

See docs/superpowers/specs/2026-08-17-dynamic-judgment-search-design.md.
Storing the result (upsert_document + write_judgment + citation
extraction) is a deliberate follow-up task, not built here — this module
only finds a real judgment and runs it through the Source Verification
Gate. Nothing here writes to Postgres or Neo4j.

Flow per lookup, matching the design doc:
1. Check the DB (title word-overlap over document_type='judgment' — not
   embedding similarity, since documents are embedded on full_text and a
   short case-name query sits far from even the correct match: measured
   distance ~0.6 to a known real match, confirmed live 2026-08-18).
2. Bharat Courts' ArchiveClient — the public Vanga AWS Open Data archive
   for the Supreme Court and any state High Court, no CAPTCHA. Confirmed
   live 2026-08-18 for both court='sci' and court='delhi'.
3. Indian Kanoon — public aggregator, last resort, labeled as such.
4. verify_batch (same gate as India Code — no lighter bar).

Note: ArchiveClient.fetch_pdf downloads a whole year's PDF bundle
(hundreds of MB) into a local cache on first use for that year/court —
this is the SDK's own caching, not something this module controls.
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
    document: Optional[CanonicalDocument] = None
    verified: Optional[bool] = None
    notes: list[str] = field(default_factory=list)


def _text_check(doc: CanonicalDocument) -> bool:
    return len(doc.full_text.strip()) >= 200


def _verify(document: CanonicalDocument) -> tuple[bool, list[str]]:
    result = verify_batch([document], text_check=_text_check)
    return result.passed, result.notes


def _check_db(query: str) -> Optional[JudgmentSearchResult]:
    query_words = {w.lower() for w in _WORD_RE.findall(query)}
    if not query_words:
        return None

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT document_id FROM documents WHERE document_type = 'judgment'")
            judgment_ids = [row[0] for row in cur.fetchall()]

        best_doc: Optional[CanonicalDocument] = None
        best_overlap = 0.0
        for document_id in judgment_ids:
            doc = get_document(conn, document_id)
            if doc is None:
                continue
            title_words = {w.lower() for w in _WORD_RE.findall(doc.title)}
            if not title_words:
                continue
            overlap = len(query_words & title_words) / len(query_words)
            if overlap > best_overlap:
                best_overlap = overlap
                best_doc = doc
    finally:
        conn.close()

    if best_doc is not None and best_overlap >= DB_TITLE_WORD_OVERLAP_THRESHOLD:
        return JudgmentSearchResult(
            found=True,
            source="database",
            document=best_doc,
            verified=True,
            notes=[f"already in DB, title word overlap={best_overlap:.2f}, no network call made"],
        )
    return None


def _archive_pdf_url(judgment) -> tuple[str, bool]:
    """Real public HTTPS URL for a judgment's PDF, plus whether it's a
    single-document link (True) or a bundled multi-document archive that
    happens to contain it (False, currently only SCI — see fetch_sci_pdf
    in the SDK: SCI PDFs ship as one tar per year, no per-document URL).
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


def _search_bharat_courts_archive(
    query: str, year: int | tuple[int, int] | None
) -> Optional[CanonicalDocument]:
    import bharat_courts as bc

    async def _search_and_fetch():
        async with bc.ArchiveClient() as client:
            results = await client.search(party=query, year=year, limit=3)
            if not results:
                return None, None
            judgment = results[0]
            pdf_bytes = await client.fetch_pdf(judgment)
            return judgment, pdf_bytes

    judgment, pdf_bytes = asyncio.run(_search_and_fetch())
    if judgment is None:
        return None

    reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
    full_text = "\n".join(page.extract_text() or "" for page in reader.pages)

    document_id = f"judgment:{(judgment.cnr or judgment.case_id or content_hash(judgment.title or query)[:12]).lower()}"
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
        title=judgment.title or query,
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


def _search_indian_kanoon(query: str) -> Optional[CanonicalDocument]:
    response = polite_get(IK_SEARCH_URL, params={"formInput": query})
    if response.status_code != 200:
        return None
    soup = BeautifulSoup(response.text, "html.parser")
    result_title = soup.find(class_="result_title")
    if result_title is None:
        return None
    link = result_title.find("a")
    if link is None or not link.get("href"):
        return None
    match = IK_DOC_ID_RE.search(link["href"])
    if match is None:
        return None
    doc_id = match.group(1)
    title = link.get_text(strip=True)

    doc_url = f"https://indiankanoon.org/doc/{doc_id}/"
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


def search_judgment(
    query: str, year: int | tuple[int, int] | None = None
) -> JudgmentSearchResult:
    """Find a real judgment for `query` (case name or citation).

    `year` (single year or inclusive (start, end) range) is strongly
    recommended: the Bharat Courts archive scans the Supreme Court plus
    all ~25 High Court partitions when no court is specified, and a year
    filter enables partition pruning — confirmed live 2026-08-18, ~23s
    with a year filter vs. >90s (didn't finish) without one.

    Does not store anything — see module docstring. Caller decides what
    to do with a found-and-verified CanonicalDocument (e.g. hand it to
    upsert_document + write_judgment once that step is built).
    """
    db_hit = _check_db(query)
    if db_hit is not None:
        return db_hit

    document = _search_bharat_courts_archive(query, year)
    source: SourceName = "bharat_courts_archive"
    if document is None:
        document = _search_indian_kanoon(query)
        source = "indian_kanoon"

    if document is None:
        notes = [f"no result for {query!r} in DB, Bharat Courts archive, or Indian Kanoon"]
        if year is None:
            notes.append("no year was given — pass one if known, it materially improves archive recall/speed")
        return JudgmentSearchResult(found=False, source="none", notes=notes)

    passed, notes = _verify(document)
    if source == "bharat_courts_archive" and year is None:
        notes.append("found without a year filter — this query scanned every partition, consider passing year")
    return JudgmentSearchResult(found=True, source=source, document=document, verified=passed, notes=notes)
