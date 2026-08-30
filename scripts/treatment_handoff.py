# scripts/treatment_handoff.py
"""Dump citation passages for classification, and apply the verdicts back.

Run: .venv/bin/python -m scripts.treatment_handoff dump  --out FILE [--batch N]
     .venv/bin/python -m scripts.treatment_handoff apply --in  FILE

`scripts/classify_treatments.py` sends passages to the configured model
chain. This does the same work with the classifier out of process, so a
stronger reader can take the passages directly. Measured 2026-08-29: the
Gemini models were quota-exhausted and the chain fell through to Gemma at
~2.75 minutes a call, which put a full pass at roughly thirteen hours.

Prioritises by *target*, most-cited first, because good_law needs EVERY edge
into a judgment classified before it can say anything but NOT_CHECKED. Half
the edges into a landmark is worth nothing; all of them is worth an answer.

Only CITES.treatment and CITES.treatment_why are written.
"""

from __future__ import annotations

import argparse
import json

from legal_ai.agents.treatment import Treatment
from legal_ai.graphdb.client import get_driver
from legal_ai.ingestion.citations import extract_citation_contexts, normalise_citation
from legal_ai.knowledge.static.db import get_connection

CONTEXT_CHARS = 700


def dump(path: str, batch: int, min_indegree: int) -> None:
    driver = get_driver()
    conn = get_connection()
    try:
        with driver.session() as session:
            rows = session.run(
                """
                MATCH (a:Judgment)-[r:CITES]->(b:Judgment)
                WITH b, count(r) AS indeg
                WHERE indeg >= $min_indegree
                MATCH (a:Judgment)-[r:CITES]->(b)
                WHERE r.treatment IS NULL AND b.citation_key IS NOT NULL
                RETURN a.document_id AS citing, b.document_id AS cited,
                       b.citation_key AS cited_key, b.title AS cited_title, indeg
                ORDER BY indeg DESC
                LIMIT $batch
                """,
                min_indegree=min_indegree,
                batch=batch,
            ).values()

        items = []
        texts: dict[str, str] = {}
        for citing, cited, cited_key, cited_title, _indeg in rows:
            if citing not in texts:
                row = conn.execute(
                    "SELECT full_text FROM documents WHERE document_id = %s", (citing,)
                ).fetchone()
                texts[citing] = (row[0] if row else "") or ""
            by_key: dict[str, str] = {}
            for citation, context in extract_citation_contexts(texts[citing]):
                by_key[normalise_citation(citation)] = context
            passage = by_key.get(cited_key)
            if not passage:
                continue
            middle = len(passage) // 2
            half = CONTEXT_CHARS // 2
            items.append({
                "citing": citing,
                "cited": cited,
                "cited_title": (cited_title or "")[:70],
                "passage": " ".join(
                    passage[max(middle - half, 0): middle + half].split()
                ),
            })
    finally:
        driver.close()
        conn.close()

    with open(path, "w") as handle:
        json.dump(items, handle, indent=1)
    print(f"{len(items)} passages -> {path}")


def apply(path: str) -> None:
    with open(path) as handle:
        items = json.load(handle)

    valid = {t.value for t in Treatment} - {Treatment.NOT_CHECKED.value}
    driver = get_driver()
    written = 0
    counts: dict[str, int] = {}
    try:
        with driver.session() as session:
            for item in items:
                treatment = str(item.get("treatment", "")).strip().upper()
                if treatment not in valid:
                    # Anything unrecognised stays unclassified. Silence is
                    # not approval -- see agents/treatment.py.
                    continue
                session.run(
                    """
                    MATCH (a:Judgment {document_id: $citing})
                          -[r:CITES]->
                          (b:Judgment {document_id: $cited})
                    SET r.treatment = $treatment, r.treatment_why = $why
                    """,
                    citing=item["citing"], cited=item["cited"],
                    treatment=treatment, why=str(item.get("why", ""))[:120],
                )
                written += 1
                counts[treatment] = counts.get(treatment, 0) + 1
    finally:
        driver.close()

    print(f"edges treated: {written}")
    for treatment, n in sorted(counts.items(), key=lambda kv: -kv[1]):
        print(f"  {treatment:14} {n}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("dump", "apply"))
    parser.add_argument("--out", default="passages.json")
    parser.add_argument("--in", dest="infile", default="passages.json")
    parser.add_argument("--batch", type=int, default=60)
    parser.add_argument("--min-indegree", type=int, default=5)
    args = parser.parse_args()
    if args.mode == "dump":
        dump(args.out, args.batch, args.min_indegree)
    else:
        apply(args.infile)


if __name__ == "__main__":
    main()
