"""Structured metadata: shared SQL filters, plus exact lookup as a signal.

Two sides of one concern. MetadataFilters constrains the other signals in
SQL; search_metadata is itself a signal, resolving a statutory reference
such as "Section 18 of the ... Act, 2016" straight to a document id --
something neither vector similarity nor keyword matching does reliably.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import psycopg

from legal_ai.ingestion.statute_citations import extract_section_references
from legal_ai.knowledge.static.store import find_act_by_name, get_document

# An exact match is either right or absent, so every hit scores the same;
# hybrid.py fuses on rank, not score.
EXACT_MATCH_SCORE = 1.0


@dataclass(frozen=True)
class MetadataFilters:
    document_type: str | None = None
    court: str | None = None
    act_id: str | None = None
    decision_date_from: date | None = None
    decision_date_to: date | None = None

    def to_sql(self, alias: str = "") -> tuple[str, list]:
        """SQL fragment (starting with ' AND ', or empty) plus its params.

        `alias` qualifies the column names for queries that join, e.g.
        alias="d" yields "d.document_type = %s".

        Filtering in SQL rather than in Python means a signal's LIMIT
        applies to rows that already passed the filter.
        """
        prefix = f"{alias}." if alias else ""
        clauses: list[str] = []
        params: list = []

        if self.document_type is not None:
            clauses.append(f"{prefix}document_type = %s")
            params.append(self.document_type)
        if self.court is not None:
            clauses.append(f"{prefix}court = %s")
            params.append(self.court)
        if self.act_id is not None:
            clauses.append(f"{prefix}act_id = %s")
            params.append(self.act_id)
        if self.decision_date_from is not None:
            clauses.append(f"{prefix}decision_date >= %s")
            params.append(self.decision_date_from)
        if self.decision_date_to is not None:
            clauses.append(f"{prefix}decision_date <= %s")
            params.append(self.decision_date_to)

        if not clauses:
            return "", []
        return " AND " + " AND ".join(clauses), params


def _passes_filters(doc, filters: MetadataFilters | None) -> bool:
    if filters is None:
        return True
    if filters.document_type is not None and doc.document_type != filters.document_type:
        return False
    if filters.court is not None and doc.court != filters.court:
        return False
    if filters.act_id is not None and doc.act_id != filters.act_id:
        return False
    if filters.decision_date_from is not None and (
        doc.decision_date is None or doc.decision_date < filters.decision_date_from
    ):
        return False
    if filters.decision_date_to is not None and (
        doc.decision_date is None or doc.decision_date > filters.decision_date_to
    ):
        return False
    return True


def search_metadata(
    conn: psycopg.Connection,
    query: str,
    limit: int = 10,
    filters: MetadataFilters | None = None,
) -> list[tuple[str, float]]:
    """Resolve statutory references in `query` to exact document ids.

    Returns [] when the query holds no recognisable statutory reference --
    normal for a plain natural-language question, not a failure. The other
    signals carry the query in that case.
    """
    results: list[tuple[str, float]] = []
    seen: set[str] = set()

    for reference in extract_section_references(query):
        act_id = find_act_by_name(conn, reference.act_name)
        if act_id is None:
            continue
        document_id = f"{act_id}:sec-{reference.section_number}"
        if document_id in seen:
            continue
        doc = get_document(conn, document_id)
        if doc is None or not _passes_filters(doc, filters):
            continue
        seen.add(document_id)
        results.append((document_id, EXACT_MATCH_SCORE))
        if len(results) >= limit:
            break

    return results
