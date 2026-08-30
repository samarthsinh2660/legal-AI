# scripts/backfill_treatment_table.py
"""Write CITES.treatment from the reporter's Case Law Reference table.

Run: .venv/bin/python -m scripts.backfill_treatment_table

Free and deterministic -- no model calls. 36% of stored Supreme Court
judgments print an editorial table saying how they treated each authority
(see ingestion/treatment_table.py); this reads it and writes the edges.

Run this BEFORE scripts/classify_treatments.py, which then only spends
model calls on the judgments that have no table.

Existing treatments are overwritten only when this source disagrees and is
stronger, because the reporter's own classification outranks a model's
reading of the same judgment.
"""

from __future__ import annotations

from legal_ai.graphdb.client import get_driver
from legal_ai.ingestion.treatment_table import extract_treatment_table
from legal_ai.knowledge.static.db import get_connection


def main() -> None:
    conn = get_connection()
    rows = conn.execute(
        "SELECT document_id, full_text FROM documents "
        "WHERE document_type = 'judgment' AND court = 'Supreme Court of India'"
    ).fetchall()
    print(f"{len(rows)} Supreme Court judgments")

    driver = get_driver()
    with_table = written = 0
    counts: dict[str, int] = {}
    try:
        with driver.session() as session:
            for n, (document_id, text) in enumerate(rows, start=1):
                table = extract_treatment_table(text or "")
                if not table:
                    continue
                with_table += 1
                for citation, treatment in table:
                    key = "".join(ch for ch in citation.upper() if ch.isalnum())
                    result = session.run(
                        """
                        MATCH (a:Judgment {document_id: $citing})
                              -[r:CITES]->(b:Judgment {citation_key: $key})
                        SET r.treatment = $treatment,
                            r.treatment_why = 'reporter Case Law Reference table'
                        RETURN count(r) AS n
                        """,
                        citing=document_id, key=key, treatment=treatment.value,
                    ).single()
                    if result and result["n"]:
                        written += result["n"]
                        counts[treatment.value] = counts.get(treatment.value, 0) + result["n"]
                if n % 2000 == 0:
                    print(f"  {n}/{len(rows)}, {written} edges", flush=True)
    finally:
        driver.close()
        conn.close()

    print(f"judgments with a table : {with_table}")
    print(f"edges treated          : {written}")
    for treatment, count in sorted(counts.items(), key=lambda kv: -kv[1]):
        print(f"  {treatment:14} {count}")


if __name__ == "__main__":
    main()
