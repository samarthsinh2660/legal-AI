# scripts/rebuild_citation_edges.py
"""Recompute judgment-to-judgment CITES edges over the whole stored corpus.

Run: .venv/bin/python -m scripts.rebuild_citation_edges

Why a separate pass: write_judgment resolves a citation against judgments
already in the graph, so during a sequential ingest an edge can only ever
point backwards -- a case cited before it was stored never resolves. Doing
it corpus-wide once, after ingest, is the only way every pair gets a chance.

Touches CITES and citation_key only. CITES_SECTION, DECIDED_BY and every
statute node are left exactly as they are.
"""

from __future__ import annotations

from legal_ai.graphdb.client import get_driver
from legal_ai.ingestion.citations import extract_citations, normalise_citation
from legal_ai.knowledge.static.db import get_connection


def main() -> None:
    conn = get_connection()
    rows = conn.execute(
        "SELECT document_id, citation, full_text FROM documents "
        "WHERE document_type = 'judgment'"
    ).fetchall()
    print(f"{len(rows)} judgments")

    # document_id of every judgment, keyed by its own normalised citation.
    by_key: dict[str, str] = {}
    for doc_id, citation, _text in rows:
        if citation:
            by_key[normalise_citation(citation)] = doc_id
    print(f"{len(by_key)} carry a citation of their own to be cited by")

    driver = get_driver()
    try:
        with driver.session() as session:
            session.run("MATCH ()-[r:CITES]->() DELETE r")
            session.run("MATCH (j:Judgment) REMOVE j.dangling_citations")

            for doc_id, citation, _text in rows:
                session.run(
                    "MATCH (j:Judgment {document_id: $id}) SET j.citation_key = $key",
                    id=doc_id,
                    key=normalise_citation(citation) if citation else None,
                )

            resolved = dangling = 0
            for doc_id, _citation, text in rows:
                cited = extract_citations(text)
                hits, misses = [], []
                for reference in cited:
                    key = normalise_citation(reference)
                    target = by_key.get(key)
                    # A judgment's own citation appears in its own header;
                    # that is not a citation of anything.
                    if target is not None and target != doc_id:
                        hits.append(target)
                    elif target is None:
                        misses.append(reference)
                if hits:
                    session.run(
                        """
                        MATCH (a:Judgment {document_id: $id})
                        UNWIND $targets AS t
                        MATCH (b:Judgment {document_id: t})
                        MERGE (a)-[:CITES]->(b)
                        """,
                        id=doc_id,
                        targets=list(set(hits)),
                    )
                if misses:
                    session.run(
                        "MATCH (a:Judgment {document_id: $id}) "
                        "SET a.dangling_citations = $misses",
                        id=doc_id,
                        misses=misses,
                    )
                resolved += len(set(hits))
                dangling += len(misses)

            edges = session.run("MATCH ()-[r:CITES]->() RETURN count(r)").single()[0]
            cited_docs = session.run(
                "MATCH (:Judgment)-[:CITES]->(b:Judgment) RETURN count(DISTINCT b)"
            ).single()[0]
            citing_docs = session.run(
                "MATCH (a:Judgment)-[:CITES]->(:Judgment) RETURN count(DISTINCT a)"
            ).single()[0]
    finally:
        driver.close()
        conn.close()

    print(f"CITES edges        : {edges}")
    print(f"  judgments citing : {citing_docs}")
    print(f"  judgments cited  : {cited_docs}")
    print(f"unresolved refs    : {dangling}")


if __name__ == "__main__":
    main()
