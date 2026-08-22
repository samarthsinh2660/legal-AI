"""Query tools for Supreme Court / High Court judgments.

See docs/superpowers/specs/2026-08-19-phase2-milestone4-tool-contracts-design.md.

search_judgments returns 0 or 1 Evidence, never a ranked list: the
underlying fetch-verify-store flow surfaces one best candidate per source.
It is a lookup, not ranked search like search_statutes.
"""

from __future__ import annotations

from legal_ai.ingestion.judgments.dynamic_search import search_judgment
from legal_ai.ingestion.judgments.store import store_judgment
from legal_ai.knowledge.static.db import get_connection
from legal_ai.knowledge.static.store import get_document
from legal_ai.retrieval.evidence_builder import to_evidence
from legal_ai.schemas.evidence import Evidence


def search_judgments(
    query: str,
    year: int | tuple[int, int] | None = None,
    store: bool = True,
    skip_db: bool = False,
    live: bool = True,
) -> list[Evidence]:
    """`skip_db=True` forces a fresh live search even if a cached DB
    match exists — use when a previous cached match turned out to be the
    wrong document (see dynamic_search.search_judgment's docstring).

    `live=False` restricts the search to what is already stored. Interactive
    callers should pass it: the live path scans every archive partition when
    no court is given, measured at 228s for a query that found nothing."""
    result = search_judgment(query, year=year, skip_db=skip_db, live=live)
    if not result.found or result.document is None:
        return []

    if store and result.source != "database" and result.verified:
        store_judgment(result.document)

    return [to_evidence(result.document)]


def get_judgment(document_id: str) -> Evidence | None:
    conn = get_connection()
    try:
        doc = get_document(conn, document_id)
    finally:
        conn.close()
    return to_evidence(doc) if doc is not None else None
