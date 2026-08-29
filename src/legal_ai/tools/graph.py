"""Query tools over the judgment/statute citation graph.

See docs/superpowers/specs/2026-08-19-phase2-milestone4-tool-contracts-design.md.

Matches come from Neo4j, which holds only document_id/title, so each needs
a Postgres round-trip via get_document to fill Evidence.content.
"""

from __future__ import annotations

from legal_ai.graphdb.client import get_driver
from legal_ai.knowledge.static.db import get_connection
from legal_ai.knowledge.static.store import get_document
from legal_ai.retrieval.authority import Authority, rank_by_authority
from legal_ai.retrieval.evidence_builder import to_evidence
from legal_ai.schemas.evidence import Evidence


def _resolve_all(document_ids: list[str]) -> list[Evidence]:
    if not document_ids:
        return []
    conn = get_connection()
    try:
        docs = [get_document(conn, doc_id) for doc_id in document_ids]
    finally:
        conn.close()
    return [to_evidence(doc) for doc in docs if doc is not None]


def find_citations(judgment_id: str) -> list[Evidence]:
    driver = get_driver()
    try:
        with driver.session() as session:
            result = session.run(
                """
                MATCH (a:Judgment {document_id: $id})-[:CITES]->(b:Judgment)
                RETURN b.document_id AS document_id
                """,
                id=judgment_id,
            )
            document_ids = [record["document_id"] for record in result]
    finally:
        driver.close()
    return _resolve_all(document_ids)


def find_section_citations(section_id: str) -> list[Evidence]:
    driver = get_driver()
    try:
        with driver.session() as session:
            result = session.run(
                """
                MATCH (j:Judgment)-[:CITES_SECTION]->(s:Section {document_id: $id})
                RETURN j.document_id AS document_id
                """,
                id=section_id,
            )
            document_ids = [record["document_id"] for record in result]
    finally:
        driver.close()
    return _resolve_all(document_ids)


def find_judgment_sections(judgment_id: str) -> list[Evidence]:
    driver = get_driver()
    try:
        with driver.session() as session:
            result = session.run(
                """
                MATCH (j:Judgment {document_id: $id})-[:CITES_SECTION]->(s:Section)
                RETURN s.document_id AS document_id
                """,
                id=judgment_id,
            )
            document_ids = [record["document_id"] for record in result]
    finally:
        driver.close()
    return _resolve_all(document_ids)


def find_leading_authorities(section_id: str, limit: int = 5) -> list[Evidence]:
    """The judgments on `section_id` that carry the most authority.

    find_section_citations returns everything citing a section in no
    meaningful order. This ranks them, which is the difference between a
    list and an answer: on a heavily-litigated provision the first is
    dozens of judgments a reader must triage themselves.

    Ranking is legal_ai.retrieval.authority -- citation count first, bench
    size as the tie-breaker. Both come from data already stored: CITES
    in-degree from Neo4j, bench_size from the backfilled column.

    Citation counts are computed over the stored corpus only. A judgment
    cited a thousand times in the reports shows zero here if we hold none
    of the citing cases, so this ranks what we can see, not the law.
    """
    driver = get_driver()
    try:
        with driver.session() as session:
            result = session.run(
                """
                MATCH (j:Judgment)-[:CITES_SECTION]->(:Section {document_id: $id})
                OPTIONAL MATCH (citing:Judgment)-[:CITES]->(j)
                RETURN j.document_id AS document_id,
                       count(DISTINCT citing) AS citation_count
                """,
                id=section_id,
            )
            counts = {r["document_id"]: r["citation_count"] for r in result}
    finally:
        driver.close()

    if not counts:
        return []

    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT document_id, bench_size FROM documents "
            "WHERE document_id = ANY(%s)",
            (list(counts),),
        ).fetchall()
    finally:
        conn.close()

    ranked = rank_by_authority(
        [
            Authority(
                document_id=document_id,
                citation_count=counts.get(document_id, 0),
                bench_size=bench_size,
            )
            for document_id, bench_size in rows
        ]
    )
    return _resolve_all([item.document_id for item in ranked[:limit]])
