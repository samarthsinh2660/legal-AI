# scripts/backfill_section_relevance.py
"""Recompute CITES_SECTION edges with a mention count.

Run: .venv/bin/python -m scripts.backfill_section_relevance

The edge was created from a single regex hit, so it recorded only that a
judgment named a section -- not whether the judgment was about it. A money
laundering case naming NI Act s.138 once produced the same edge as a cheque
dishonour case that turns on it, and asking for the leading authorities on
s.138 could return the former above the latter.

This recounts from the stored text and writes `mentions` onto each edge.
Existing edges are updated in place, not deleted: CITES, DECIDED_BY and
every statute node are left exactly as they are.

Safe to re-run -- it recomputes from full_text, which does not change.
"""

from __future__ import annotations

from legal_ai.graphdb.client import get_driver
from legal_ai.ingestion.statute_citations import extract_section_references
from legal_ai.knowledge.static.db import get_connection
from legal_ai.knowledge.static.store import find_act_by_name


def main() -> None:
    conn = get_connection()
    rows = conn.execute(
        "SELECT document_id, full_text FROM documents WHERE document_type = 'judgment'"
    ).fetchall()
    print(f"{len(rows)} judgments")

    driver = get_driver()
    updated = passing = substantive = 0
    try:
        with driver.session() as session:
            for n, (document_id, text) in enumerate(rows, start=1):
                for ref in extract_section_references(text):
                    act_id = find_act_by_name(conn, ref.act_name)
                    if not act_id:
                        continue
                    section_id = f"{act_id}:sec-{ref.section_number}"
                    result = session.run(
                        """
                        MATCH (j:Judgment {document_id: $doc_id})
                              -[r:CITES_SECTION]->
                              (:Section {document_id: $section_id})
                        SET r.mentions = $mentions
                        RETURN count(r) AS n
                        """,
                        doc_id=document_id,
                        section_id=section_id,
                        mentions=ref.mentions,
                    ).single()
                    if result and result["n"]:
                        updated += result["n"]
                        if ref.mentions >= 2:
                            substantive += 1
                        else:
                            passing += 1
                if n % 1000 == 0:
                    print(f"  {n}/{len(rows)} judgments, {updated} edges", flush=True)
    finally:
        driver.close()
        conn.close()

    print(f"edges updated      : {updated}")
    print(f"  substantive (2+) : {substantive}")
    print(f"  passing (1)      : {passing}")


if __name__ == "__main__":
    main()
