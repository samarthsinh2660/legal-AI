"""Query tools for Acts and Sections — Phase 2 Milestone 4.

See docs/superpowers/specs/2026-08-19-phase2-milestone4-tool-contracts-design.md.
Thin wrappers over the Phase 1 static store — no new fetching or
verification logic here, just Evidence construction.
"""

from __future__ import annotations

from legal_ai.knowledge.static.db import get_connection
from legal_ai.knowledge.static.embeddings import embed
from legal_ai.knowledge.static.store import find_similar, get_document
from legal_ai.retrieval.evidence_builder import to_evidence
from legal_ai.schemas.evidence import Evidence

_STATUTE_TYPES = {"act", "section"}

# find_similar has no document_type filter, so over-fetch and filter in
# Python — cheap at this corpus size, and avoids changing a function
# several other callers already depend on for an unfiltered result.
_OVERFETCH_FACTOR = 5


def search_statutes(query: str, limit: int = 5) -> list[Evidence]:
    conn = get_connection()
    try:
        candidates = find_similar(conn, embed(query), limit=limit * _OVERFETCH_FACTOR)
    finally:
        conn.close()

    matches = [doc for doc, _distance in candidates if doc.document_type in _STATUTE_TYPES]
    return [to_evidence(doc) for doc in matches[:limit]]


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
