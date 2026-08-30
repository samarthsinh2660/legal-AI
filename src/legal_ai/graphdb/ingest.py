# src/legal_ai/graphdb/ingest.py
"""Write CONTAINS / CITES / CITES_SECTION / DECIDED_BY edges — structural
only, no LLM.

Semantic relationships (INTERPRETED_BY, DISTINGUISHES, OVERRULES) are
Phase 7 (GraphRAG) work — see docs/phases/PHASE_7_ADVANCED_GRAPHRAG.md.
"""

from __future__ import annotations

import neo4j
import psycopg

from legal_ai.ingestion.citations import extract_citations, normalise_citation
from legal_ai.ingestion.schema import CanonicalDocument
from legal_ai.ingestion.statute_citations import extract_section_references
from legal_ai.ingestion.treatment_table import extract_treatment_table
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
    # Identifies THIS document for other judgments' CITES edges to
    # resolve against, so it must be the document's own known citation --
    # never inferred from a citation its body text merely mentions, which
    # would mislabel it as being the case it cites.
    own_citation = judgment.citation

    with driver.session() as session:
        session.run(
            """
            MERGE (j:Judgment {document_id: $doc_id})
            SET j.title = $title,
                j.citation = $citation,
                j.citation_key = $citation_key
            """,
            doc_id=judgment.document_id,
            title=judgment.title,
            citation=own_citation,
            citation_key=normalise_citation(own_citation) if own_citation else None,
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
                MATCH (b:Judgment {citation_key: $cited_key})
                WHERE a.document_id <> b.document_id
                MERGE (a)-[:CITES]->(b)
                RETURN b.document_id AS resolved
                """,
                citing_id=judgment.document_id,
                cited_key=normalise_citation(cited_citation),
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

        # Treatment, where the reporter states it. Free and deterministic:
        # Supreme Court Reports print how the judgment dealt with each
        # authority, so a newly stored judgment carries its treatments
        # immediately instead of waiting for a backfill. Judgments without
        # such a table are left untreated for scripts/classify_treatments.py,
        # which spends model budget and should stay deliberate.
        #
        # After the CITES edges above, because it sets a property on them.
        for citation, treatment in extract_treatment_table(judgment.full_text):
            session.run(
                """
                MATCH (a:Judgment {document_id: $doc_id})
                      -[r:CITES]->(b:Judgment {citation_key: $key})
                SET r.treatment = $treatment,
                    r.treatment_why = 'reporter Case Law Reference table'
                """,
                doc_id=judgment.document_id,
                key=normalise_citation(citation),
                treatment=treatment.value,
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
                        MERGE (j)-[r:CITES_SECTION]->(s)
                        SET r.mentions = $mentions
                        """,
                        doc_id=judgment.document_id,
                        section_id=section_id,
                        mentions=ref.mentions,
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
