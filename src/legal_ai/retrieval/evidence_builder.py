"""Canonical documents -> Evidence, with provenance intact.

See docs/superpowers/specs/2026-08-19-phase2-milestone5-hybrid-retrieval-design.md.

The single home for this conversion. tools/statutes.py, tools/judgments.py
and tools/graph.py each had their own identical private copy; they now
import to_evidence from here.

No score field is set: the returned list is already ordered by the fusion
that produced it, and adding an unused field would be speculative.
"""

from __future__ import annotations

import psycopg

from legal_ai.ingestion.schema import CanonicalDocument
from legal_ai.knowledge.static.store import get_document
from legal_ai.schemas.evidence import Evidence


def to_evidence(doc: CanonicalDocument) -> Evidence:
    return Evidence(
        content=doc.full_text,
        document_id=doc.document_id,
        title=doc.title,
        document_type=doc.document_type,
        provenance=doc.provenance,
    )


def build_evidence(conn: psycopg.Connection, document_ids: list[str]) -> list[Evidence]:
    """Fetch documents for `document_ids`, preserving that order.

    An id with no stored document is skipped rather than raising: the graph
    can legitimately hold a node whose Postgres row was never stored, and
    dropping it is honest -- inventing a placeholder would not be.

    One round-trip per id is fine here: this runs on the fused top-K
    (single digits), not on a whole result set.
    """
    evidence: list[Evidence] = []
    for document_id in document_ids:
        doc = get_document(conn, document_id)
        if doc is not None:
            evidence.append(to_evidence(doc))
    return evidence
