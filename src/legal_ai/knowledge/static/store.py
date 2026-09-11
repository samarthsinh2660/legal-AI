"""CRUD + similarity search over the canonical documents table."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime

import psycopg

from legal_ai.ingestion.schema import CanonicalDocument
from legal_ai.schemas.evidence import Provenance

# Abbreviations and short names judgments write, each pinned to the one Act
# it means. A table and not a match, because none of these can be found in
# a title: "IPC" is not in "The Indian Penal Code, 1860". Every target is
# checked to exist by tests/retrieval/test_act_resolution.py.
#
# Left out on purpose: "Arbitration Act" (1940 or 1996), "Companies Act"
# (1956 or 2013), "Succession Act" (Indian or Hindu), "Representation of
# the People Act" (1950 rolls or 1951 elections). A name that means two Acts
# is refused rather than resolved -- see find_act_by_name.
_ALIASES: dict[str, str] = {
    **dict.fromkeys(("ipc", "i.p.c.", "indian penal code", "penal code"), "act:ipc-1860"),
    **dict.fromkeys(("crpc", "cr.p.c.", "cr. p.c.", "code of criminal procedure",
                     "criminal procedure code"), "act:crpc-1973"),
    **dict.fromkeys(("cpc", "c.p.c.", "code of civil procedure",
                     "civil procedure code"), "act:2191"),
    **dict.fromkeys(("evidence act", "indian evidence act", "iea"), "act:iea-1872"),
    **dict.fromkeys(("ni act", "n.i. act", "negotiable instruments act",
                     "negotiable instrument act"), "act:2189"),
    **dict.fromkeys(("a&c act", "arbitration and conciliation act",
                     "arbitration & conciliation act"), "act:1978"),
    **dict.fromkeys(("pml act", "pmla", "pmla act"), "act:2036"),
    **dict.fromkeys(("ibc", "i&b code", "insolvency and bankruptcy code"), "act:2154"),
    **dict.fromkeys(("bns", "bharatiya nyaya sanhita"), "act:20062"),
    **dict.fromkeys(("bnss", "bharatiya nagarik suraksha sanhita"), "act:20099"),
    **dict.fromkeys(("bsa", "bharatiya sakshya adhiniyam", "bharatiya sakshya act"),
                    "act:20063"),
    **dict.fromkeys(("motor vehicle act", "mv act", "m.v. act"), "act:1798"),
    # Short names for titles whose parenthetical a judgment never writes out.
    "aadhaar act": "act:2160",
    "juvenile justice act": "act:2148",
    "ndps act": "act:1791",
    "sarfaesi act": "act:2006",
    "pocso act": "act:2079",
    "sebi act": "act:1890",
    "msmed act": "act:2013",
    "mmdr act": "act:1421",
    "rte act": "act:2086",
    "ngt act": "act:2025",
    "nia act": "act:2054",
}

# Names that mean one held Act only when the judgment says which year.
# "Arbitration Act, 1996" is the Arbitration and Conciliation Act; "the
# Arbitration Act, 1940" is a repealed law we do not hold. With no year --
# after `extract_section_references` has carried over any the judgment wrote
# -- it is refused rather than assumed to be the newer one.
_ALIASES_WITH_YEAR: dict[str, str] = {
    "arbitration act": "act:1978",
}

# What a judgment calls an Act when it is describing it rather than naming
# it. Each is the tail of some title -- "The Andhra State Act, 1953" ends in
# "State Act" -- so a name rule alone matched 22 references to it, and "a
# State Act" in a judgment means whichever State's law is in issue.
_DESCRIPTIONS = frozenset({
    "act", "code", "said act", "said code", "state act", "central act",
    "principal act", "parent act", "amendment act", "amending act", "present act",
    "old act", "new act", "earlier act", "repealed act", "local act", "special act",
    "general act", "enabling act", "impugned act", "unlawful act",
})

_YEAR_IN_TITLE = re.compile(r",?\s*\b(1[89]\d\d|20\d\d)\b\.?\s*$")


def _normalise_act_name(name: str) -> str:
    """Lower-cased, one space between words, no "the" and no trailing
    punctuation. Hyphens become spaces: judgments write "Income Tax" and
    India Code prints "Income-tax"."""
    text = re.sub(r"\s+", " ", name.replace("-", " ")).strip().lower()
    # "the" is dropped wherever it falls, not only at the start: judgments
    # write "Representation of People Act" for "...of the People Act".
    text = re.sub(r"\bthe\b ?", "", text).strip()
    return text.rstrip(".,; ")


def upsert_document(
    conn: psycopg.Connection,
    doc: CanonicalDocument,
    embedding: list[float] | None = None,
) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT content_hash, title, full_text, provenance, ingested_at
            FROM documents WHERE document_id = %s
            """,
            (doc.document_id,),
        )
        row = cur.fetchone()
        if row is not None and row[0] == doc.content_hash:
            return False

        if row is not None:
            # The stored text is about to be overwritten by different
            # text -- an amendment, a correction, or a better scrape. Keep
            # the old version first: a citation to what the law said before
            # must stay checkable after the law changes.
            cur.execute(
                """
                INSERT INTO document_versions (
                    document_id, title, full_text, content_hash,
                    provenance, first_seen_at, superseded_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    doc.document_id,
                    row[1],
                    row[2],
                    row[0],
                    json.dumps(row[3]),
                    row[4],
                    doc.ingested_at,
                ),
            )

        cur.execute(
            """
            INSERT INTO documents (
                document_id, document_type, title, court, citation,
                case_number, parties, decision_date, enactment_date,
                disposal_nature, act_id, full_text, content_hash,
                provenance, ingested_at, embedding
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
            ON CONFLICT (document_id) DO UPDATE SET
                document_type = EXCLUDED.document_type,
                title = EXCLUDED.title,
                court = EXCLUDED.court,
                citation = EXCLUDED.citation,
                case_number = EXCLUDED.case_number,
                parties = EXCLUDED.parties,
                decision_date = EXCLUDED.decision_date,
                enactment_date = EXCLUDED.enactment_date,
                disposal_nature = EXCLUDED.disposal_nature,
                act_id = EXCLUDED.act_id,
                full_text = EXCLUDED.full_text,
                content_hash = EXCLUDED.content_hash,
                provenance = EXCLUDED.provenance,
                ingested_at = EXCLUDED.ingested_at,
                embedding = EXCLUDED.embedding
            """,
            (
                doc.document_id,
                doc.document_type,
                doc.title,
                doc.court,
                doc.citation,
                doc.case_number,
                json.dumps(doc.parties) if doc.parties is not None else None,
                doc.decision_date,
                doc.enactment_date,
                doc.disposal_nature,
                doc.act_id,
                doc.full_text,
                doc.content_hash,
                doc.provenance.model_dump_json(),
                doc.ingested_at,
                embedding,
            ),
        )
    conn.commit()
    return True


def _row_to_document(row: tuple) -> CanonicalDocument:
    (
        document_id, document_type, title, court, citation, case_number,
        parties, decision_date, enactment_date, disposal_nature, act_id,
        full_text, content_hash_value, provenance_json, ingested_at,
    ) = row
    return CanonicalDocument(
        document_id=document_id,
        document_type=document_type,
        title=title,
        court=court,
        citation=citation,
        case_number=case_number,
        parties=parties,
        decision_date=decision_date,
        enactment_date=enactment_date,
        disposal_nature=disposal_nature,
        act_id=act_id,
        full_text=full_text,
        content_hash=content_hash_value,
        provenance=Provenance.model_validate(provenance_json),
        ingested_at=ingested_at,
    )


def get_document(conn: psycopg.Connection, document_id: str) -> CanonicalDocument | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT document_id, document_type, title, court, citation,
                   case_number, parties, decision_date, enactment_date,
                   disposal_nature, act_id, full_text, content_hash,
                   provenance, ingested_at
            FROM documents WHERE document_id = %s
            """,
            (document_id,),
        )
        row = cur.fetchone()
    return _row_to_document(row) if row else None


def _names(title: str, name: str) -> bool:
    """Whether `title` is the Act `name` refers to.

    The name has to be where the title's own name ends, not merely inside
    it. "The Goa, Daman and Diu (Extension of the Code of Civil Procedure
    and the Arbitration Act) Regulation" contains "Arbitration Act"; it is
    not the Arbitration Act, and matching the phrase anywhere took 351
    references there.
    """
    base = _normalise_act_name(_YEAR_IN_TITLE.sub("", title))
    return base == name or base.endswith(" " + name)


def find_act_by_name(
    conn: psycopg.Connection, act_name: str, act_year: str | None = None
) -> str | None:
    """Resolve an Act as a judgment names it to the one stored Act it means.

    A wrong match writes a CITES_SECTION edge to an Act the judgment never
    mentioned, and it renders exactly like a right one -- so every rule here
    refuses rather than guesses:

    - An abbreviation resolves only through `_ALIASES`.
    - Otherwise the name must appear in a title as a whole phrase, word for
      word. The rule this replaced accepted each word anywhere, as a
      substring, and took the shortest title: "Income Tax Act" became the
      Black Money Act, "State Act" the Deo Estate Act.
    - A year, when the judgment wrote one, must be the year in the title.
    - A name more than one title answers to resolves to nothing, unless
      exactly one of them is that name and no more. "Succession Act" is the
      Indian and the Hindu Act; it is refused.
    """
    name = _normalise_act_name(act_name)
    if not name or name in _DESCRIPTIONS:
        return None

    alias = _ALIASES.get(name)
    if alias is None and act_year is not None:
        alias = _ALIASES_WITH_YEAR.get(name)
    if alias is not None:
        if act_year is None:
            return alias
        row = conn.execute(
            "SELECT title FROM documents WHERE document_id = %s", (alias,)
        ).fetchone()
        return alias if row and act_year in row[0] else None

    candidates = [
        (document_id, title)
        for document_id, title in conn.execute(
            "SELECT document_id, title FROM documents WHERE document_type = 'act'"
        ).fetchall()
        if _names(title, name) and (act_year is None or act_year in title)
    ]
    if len(candidates) == 1:
        return candidates[0][0]

    # Several titles contain the phrase -- a principal Act and the Acts
    # named after it. Only a title that IS the name, year aside, settles it.
    exact = [
        (document_id, title) for document_id, title in candidates
        if _normalise_act_name(_YEAR_IN_TITLE.sub("", title)) == name
    ]
    if len(exact) == 1:
        return exact[0][0]
    # The same title twice is one Act stored twice, not two Acts: the
    # Specific Relief Act 1963 is held as a 48-section Act and a 1-section
    # stub. The copy that holds the sections is the one a citation can land
    # on. Different titles -- two years of the same name -- stay refused.
    if len(exact) > 1 and len({title for _id, title in exact}) == 1:
        return conn.execute(
            "SELECT a.document_id FROM documents a WHERE a.document_id = ANY(%s) "
            "ORDER BY (SELECT count(*) FROM documents s WHERE s.act_id = a.document_id) DESC "
            "LIMIT 1",
            ([document_id for document_id, _title in exact],),
        ).fetchone()[0]
    return None


def find_similar(
    conn: psycopg.Connection,
    query_embedding: list[float],
    limit: int = 5,
) -> list[tuple[CanonicalDocument, float]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT document_id, document_type, title, court, citation,
                   case_number, parties, decision_date, enactment_date,
                   disposal_nature, act_id, full_text, content_hash,
                   provenance, ingested_at,
                   embedding <=> %s::vector AS distance
            FROM documents
            WHERE embedding IS NOT NULL
            ORDER BY distance ASC
            LIMIT %s
            """,
            (query_embedding, limit),
        )
        rows = cur.fetchall()
    return [(_row_to_document(row[:-1]), row[-1]) for row in rows]


@dataclass(frozen=True)
class VersionedText:
    """Text of a document as it stood at a point in time, plus what we
    actually know about the bounds of that claim.

    `is_current` says the answer came from `documents` rather than
    history. `observed_from` / `observed_until` are the ingestion times
    that bracket the version -- not commencement and repeal dates. A
    caller quoting this to a lawyer must pass that distinction on: it
    says "this is the text we had on record then", not "this is the text
    Parliament had enacted then".
    """

    document_id: str
    title: str
    full_text: str
    content_hash: str
    is_current: bool
    observed_from: datetime
    observed_until: datetime | None


def get_text_as_on(
    conn: psycopg.Connection,
    document_id: str,
    as_on: datetime,
) -> VersionedText | None:
    """The stored text of `document_id` as it stood at `as_on`.

    Which text applies is decided by the date of the cause of action, not
    the date of the question, so the current text is frequently the wrong
    one to quote. Returns the oldest superseded version that was still
    current at `as_on`; falls back to the live row when history has
    nothing that late, which is the common case for text that has never
    changed since ingestion.

    Returns None for an unknown document_id.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT title, full_text, content_hash, first_seen_at, superseded_at
            FROM document_versions
            WHERE document_id = %s AND superseded_at > %s
            ORDER BY superseded_at ASC
            LIMIT 1
            """,
            (document_id, as_on),
        )
        row = cur.fetchone()
        if row is not None:
            return VersionedText(
                document_id=document_id,
                title=row[0],
                full_text=row[1],
                content_hash=row[2],
                is_current=False,
                observed_from=row[3],
                observed_until=row[4],
            )

        cur.execute(
            """
            SELECT title, full_text, content_hash, ingested_at
            FROM documents WHERE document_id = %s
            """,
            (document_id,),
        )
        row = cur.fetchone()
    if row is None:
        return None
    return VersionedText(
        document_id=document_id,
        title=row[0],
        full_text=row[1],
        content_hash=row[2],
        is_current=True,
        observed_from=row[3],
        observed_until=None,
    )


def list_versions(conn: psycopg.Connection, document_id: str) -> list[VersionedText]:
    """Every superseded version of `document_id`, oldest first.

    Excludes the current text, which lives in `documents` -- use
    get_document for that.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT title, full_text, content_hash, first_seen_at, superseded_at
            FROM document_versions
            WHERE document_id = %s
            ORDER BY superseded_at ASC
            """,
            (document_id,),
        )
        rows = cur.fetchall()
    return [
        VersionedText(
            document_id=document_id,
            title=title,
            full_text=full_text,
            content_hash=hash_value,
            is_current=False,
            observed_from=first_seen_at,
            observed_until=superseded_at,
        )
        for title, full_text, hash_value, first_seen_at, superseded_at in rows
    ]
