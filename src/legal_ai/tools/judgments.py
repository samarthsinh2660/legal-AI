"""Query tools for Supreme Court / High Court judgments — Phase 2 Milestone 4.

See docs/superpowers/specs/2026-08-19-phase2-milestone4-tool-contracts-design.md.
search_judgments wraps the same fetch-verify-store flow already proven in
scripts/search_judgment.py's CLI — it returns 0 or 1 Evidence, never a
ranked multi-result list, since the underlying flow only ever surfaces
one best candidate per source (DB word-overlap match, or first archive/
Indian Kanoon match). Do not treat this like search_statutes' ranked
semantic search.
"""

from __future__ import annotations

from legal_ai.ingestion.judgments.dynamic_search import search_judgment
from legal_ai.ingestion.judgments.store import store_judgment
from legal_ai.ingestion.schema import CanonicalDocument
from legal_ai.knowledge.static.db import get_connection
from legal_ai.knowledge.static.store import get_document
from legal_ai.schemas.evidence import Evidence


def _to_evidence(doc: CanonicalDocument) -> Evidence:
    return Evidence(
        content=doc.full_text,
        document_id=doc.document_id,
        title=doc.title,
        document_type=doc.document_type,
        provenance=doc.provenance,
    )


def search_judgments(
    query: str,
    year: int | tuple[int, int] | None = None,
    store: bool = True,
    skip_db: bool = False,
) -> list[Evidence]:
    """`skip_db=True` forces a fresh live search even if a cached DB
    match exists — use when a previous cached match turned out to be the
    wrong document (see dynamic_search.search_judgment's docstring)."""
    result = search_judgment(query, year=year, skip_db=skip_db)
    if not result.found or result.document is None:
        return []

    if store and result.source != "database" and result.verified:
        store_judgment(result.document)

    return [_to_evidence(result.document)]


def get_judgment(document_id: str) -> Evidence | None:
    conn = get_connection()
    try:
        doc = get_document(conn, document_id)
    finally:
        conn.close()
    return _to_evidence(doc) if doc is not None else None
