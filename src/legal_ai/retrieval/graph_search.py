"""Knowledge-graph expansion -- what else connects to what we already found.

See docs/superpowers/specs/2026-08-19-phase2-milestone5-hybrid-retrieval-design.md.

Deliberately expansion rather than a standalone signal: the graph stores no
text to match a raw query against, so the only question it can answer well
is "given these documents, what is connected to them?".

Traverses the existing structural edges in both directions -- CONTAINS
(Act->Section), CITES (Judgment->Judgment), CITES_SECTION
(Judgment->Section). A document reached from more distinct seeds scores
higher, so a Section that several retrieved judgments all rely on rises.

Does not import from legal_ai.tools: tools/graph.py imports to_evidence
from retrieval/evidence_builder.py, so importing it back here would be a
circular import.
"""

from __future__ import annotations

import neo4j


def expand_via_graph(
    driver: neo4j.Driver,
    seed_document_ids: list[str],
    limit: int = 10,
) -> list[tuple[str, float]]:
    if not seed_document_ids:
        return []

    with driver.session() as session:
        result = session.run(
            """
            MATCH (seed) WHERE seed.document_id IN $seeds
            MATCH (seed)-[:CONTAINS|CITES|CITES_SECTION]-(neighbour)
            WHERE neighbour.document_id IS NOT NULL
              AND NOT neighbour.document_id IN $seeds
            RETURN neighbour.document_id AS document_id,
                   count(DISTINCT seed) AS seed_count
            ORDER BY seed_count DESC, document_id ASC
            LIMIT $limit
            """,
            seeds=seed_document_ids,
            limit=limit,
        )
        rows = [(record["document_id"], record["seed_count"]) for record in result]

    seed_total = len(seed_document_ids)
    return [(document_id, seed_count / seed_total) for document_id, seed_count in rows]
