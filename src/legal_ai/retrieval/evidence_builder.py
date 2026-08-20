"""Canonical documents -> Evidence, with provenance intact.

The single home for this conversion; tools/ imports to_evidence from here.

No score field is set -- the returned list is already ordered by whatever
produced it.
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

    Ids with no stored document are skipped rather than raising: the graph
    can hold a node whose Postgres row was never stored.

    One round-trip per id is acceptable because this runs on the fused
    top-K, not a whole result set.
    """
    evidence: list[Evidence] = []
    for document_id in document_ids:
        doc = get_document(conn, document_id)
        if doc is not None:
            evidence.append(to_evidence(doc))
    return evidence
