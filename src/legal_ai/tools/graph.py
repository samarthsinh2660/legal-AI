"""Query tools over the judgment/statute citation graph.

See docs/superpowers/specs/2026-08-19-phase2-milestone4-tool-contracts-design.md.

Matches come from Neo4j, which holds only document_id/title, so each needs
a Postgres round-trip via get_document to fill Evidence.content.
"""

from __future__ import annotations

from legal_ai.graphdb.client import get_driver
from legal_ai.knowledge.static.db import get_connection
from legal_ai.knowledge.static.store import get_document
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
