"""Query tools for Acts and Sections.

See docs/superpowers/specs/2026-08-19-phase2-milestone4-tool-contracts-design.md.

Thin wrappers over the static store: no fetching or verification logic
here, only Evidence construction.
"""

from __future__ import annotations

from legal_ai.knowledge.static.db import get_connection
from legal_ai.knowledge.static.store import get_document
from legal_ai.retrieval.evidence_builder import to_evidence
from legal_ai.retrieval.hybrid import hybrid_search
from legal_ai.schemas.evidence import Evidence

_STATUTE_TYPES = {"act", "section"}

# hybrid_search takes a single document_type, but a statute search wants both
# acts and sections, so over-fetch and filter in Python.
_OVERFETCH_FACTOR = 5


def search_statutes(query: str, limit: int = 5) -> list[Evidence]:
    """Statutes matching `query`, through the full Phase 2 pipeline.

    Uses hybrid_search -- keyword and vector fused, then reranked -- not bare
    vector similarity. Measured 2026-08-22: vector-only search here was the
    reason every research-agent benchmark scored far below plain retrieval.
    The agent was searching with a weaker tool than the one that was
    benchmarked, so its results were never comparable.
    """
    results = hybrid_search(query, limit=limit * _OVERFETCH_FACTOR)
    matches = [item for item in results if item.document_type in _STATUTE_TYPES]
    return matches[:limit]


def get_statute(act_id: str) -> Evidence | None:
    conn = get_connection()
    try:
        doc = get_document(conn, act_id)
    finally:
        conn.close()
    return to_evidence(doc) if doc is not None else None


def get_section(act_id: str, section_number: str) -> Evidence | None:
    conn = get_connection()
    try:
        doc = get_document(conn, f"{act_id}:sec-{section_number}")
    finally:
        conn.close()
    return to_evidence(doc) if doc is not None else None
