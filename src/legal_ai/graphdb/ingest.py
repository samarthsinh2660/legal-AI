# src/legal_ai/graphdb/ingest.py
"""Write CONTAINS / CITES / CITES_SECTION / DECIDED_BY edges — structural
only, no LLM.

Semantic relationships (INTERPRETED_BY, DISTINGUISHES, OVERRULES) are
Phase 7 (GraphRAG) work — see docs/phases/PHASE_7_ADVANCED_GRAPHRAG.md.
"""

from __future__ import annotations

import neo4j
import psycopg

from legal_ai.ingestion.citations import extract_citations
from legal_ai.ingestion.schema import CanonicalDocument
from legal_ai.ingestion.statute_citations import extract_section_references
from legal_ai.knowledge.static.store import find_act_by_name, get_document


def write_act_section(
    driver: neo4j.Driver,
    act: CanonicalDocument,
    section: CanonicalDocument,
) -> None:
    with driver.session() as session:
        session.run(
            """
            MERGE (a:Act {document_id: $act_id})
            SET a.title = $act_title
            MERGE (s:Section {document_id: $section_id})
            SET s.title = $section_title
            MERGE (a)-[:CONTAINS]->(s)
            """,
            act_id=act.document_id,
            act_title=act.title,
            section_id=section.document_id,
            section_title=section.title,
        )


def write_judgment(
    driver: neo4j.Driver,
    judgment: CanonicalDocument,
    pg_conn: psycopg.Connection | None = None,
) -> None:
    """`pg_conn` is optional: without it, Section reference resolution
    (CITES_SECTION) is skipped, but Judgment/CITES/DECIDED_BY still write
    — lets callers that don't care about statute cross-references opt out
    of the extra Postgres round-trips per reference.
    """
    citations_in_text = extract_citations(judgment.full_text)
    own_citation = judgment.citation or (citations_in_text[0] if citations_in_text else None)

    with driver.session() as session:
        session.run(
            """
            MERGE (j:Judgment {document_id: $doc_id})
            SET j.title = $title, j.citation = $citation
            """,
            doc_id=judgment.document_id,
            title=judgment.title,
            citation=own_citation,
        )

        if judgment.court:
            session.run(
                """
                MATCH (j:Judgment {document_id: $doc_id})
                MERGE (c:Court {name: $court})
                MERGE (j)-[:DECIDED_BY]->(c)
                """,
                doc_id=judgment.document_id,
                court=judgment.court,
            )

        for cited_citation in citations_in_text:
            result = session.run(
                """
                MATCH (a:Judgment {document_id: $citing_id})
                MATCH (b:Judgment {citation: $cited_citation})
                WHERE a.document_id <> b.document_id
                MERGE (a)-[:CITES]->(b)
                RETURN b.document_id AS resolved
                """,
                citing_id=judgment.document_id,
                cited_citation=cited_citation,
            )
            if result.single() is None:
                session.run(
                    """
                    MATCH (a:Judgment {document_id: $citing_id})
                    SET a.dangling_citations = coalesce(a.dangling_citations, []) + $citation
                    """,
                    citing_id=judgment.document_id,
                    citation=cited_citation,
                )

        if pg_conn is not None:
            for ref in extract_section_references(judgment.full_text):
                act_id = find_act_by_name(pg_conn, ref.act_name)
                section_id = f"{act_id}:sec-{ref.section_number}" if act_id else None
                resolved = section_id is not None and get_document(pg_conn, section_id) is not None

                if resolved:
                    session.run(
                        """
                        MATCH (j:Judgment {document_id: $doc_id})
                        MATCH (s:Section {document_id: $section_id})
                        MERGE (j)-[:CITES_SECTION]->(s)
                        """,
                        doc_id=judgment.document_id,
                        section_id=section_id,
                    )
                else:
                    session.run(
                        """
                        MATCH (j:Judgment {document_id: $doc_id})
                        SET j.dangling_section_citations = coalesce(j.dangling_section_citations, []) + $raw
                        """,
                        doc_id=judgment.document_id,
                        raw=ref.raw,
                    )
