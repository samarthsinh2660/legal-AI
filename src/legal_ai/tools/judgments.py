"""Query tools for Supreme Court / High Court judgments.

See docs/superpowers/specs/2026-08-19-phase2-milestone4-tool-contracts-design.md.

search_judgments returns up to `limit` Evidence. At limit=1 it is a lookup
-- the caller knows the case name. Above one it is discovery, and only the
full-text source can serve it: the archive index carries no subject,
headnote or keyword column, so a query phrased as an issue has nothing to
match there.
"""

from __future__ import annotations

from legal_ai.ingestion.judgments.dynamic_search import search_judgments as _search
from legal_ai.ingestion.judgments.store import store_judgment
from legal_ai.knowledge.static.db import get_connection
from legal_ai.knowledge.static.store import get_document
from legal_ai.retrieval.evidence_builder import to_evidence
from legal_ai.schemas.evidence import Evidence


def search_judgments(
    query: str,
    year: int | tuple[int, int] | None = None,
    limit: int = 1,
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
    result = _search(query, year=year, limit=limit, skip_db=skip_db, live=live)
    if not result.found:
        return []

    if store and result.source != "database" and result.verified:
        for document in result.documents:
            store_judgment(document)

    return [to_evidence(document) for document in result.documents]


def get_judgment(document_id: str) -> Evidence | None:
    conn = get_connection()
    try:
        doc = get_document(conn, document_id)
    finally:
        conn.close()
    return to_evidence(doc) if doc is not None else None
