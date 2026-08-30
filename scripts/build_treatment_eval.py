# scripts/build_treatment_eval.py
"""Build a frozen treatment-classification eval from reporter ground truth.

Run: .venv/bin/python -m scripts.build_treatment_eval --out evals/datasets/treatment.json

The label comes from the Supreme Court Reports' own Case Law Reference table
-- the reporter's editorial classification, which is the same source a
practitioner would check. That makes ground truth free and independent of
anything the model produced.

The passage given to the model must NOT be the table row, or the eval would
measure reading a label rather than reading law. Only occurrences of the
citation BEFORE the headnote's citation block are kept. Body prose that
happens to say "we distinguish X" is fair game -- that is the evidence the
classifier exists to read.

Frozen once and committed, so the classifier is the only variable across
runs -- the same reason evals/datasets/verification.json is frozen.
"""

from __future__ import annotations

import argparse
import json
import random
import re

from legal_ai.graphdb.client import get_driver
from legal_ai.ingestion.citations import extract_citation_contexts, normalise_citation
from legal_ai.ingestion.treatment_table import extract_treatment_table
from legal_ai.knowledge.static.db import get_connection

# Position alone separates evidence from answer. An earlier version also
# dropped any passage containing a treatment word, which was wrong: in body
# prose "we respectfully distinguish X" IS the evidence the classifier is
# meant to read, not a leaked label. Filtering it left an eval containing
# only CONSIDERED and FOLLOWED -- no DISTINGUISHED, no OVERRULED -- which
# is precisely the pair whose errors matter.
_BLOCK = re.compile(
    r"Case\s+Law\s+(Reference|Cited)|LIST\s+OF\s+CITATIONS", re.IGNORECASE
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="evals/datasets/treatment.json")
    parser.add_argument("--limit", type=int, default=120)
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()

    conn = get_connection()
    driver = get_driver()
    try:
        with driver.session() as session:
            rows = session.run(
                """
                MATCH (a:Judgment)-[r:CITES]->(b:Judgment)
                WHERE r.treatment_why = 'reporter Case Law Reference table'
                RETURN a.document_id AS citing, b.document_id AS cited,
                       b.citation_key AS key, b.title AS cited_title,
                       r.treatment AS treatment
                """
            ).values()
        print(f"{len(rows)} reporter-labelled edges")

        cases = []
        texts: dict[str, str] = {}
        for citing, cited, key, cited_title, treatment in rows:
            if citing not in texts:
                row = conn.execute(
                    "SELECT full_text FROM documents WHERE document_id = %s", (citing,)
                ).fetchone()
                texts[citing] = (row[0] if row else "") or ""
            text = texts[citing]
            if not text:
                continue

            # Where the headnote's citation block starts; occurrences after
            # it are the table itself and would hand over the answer.
            block = _BLOCK.search(text)
            body_end = block.start() if block else len(text)

            for citation, context in extract_citation_contexts(text):
                if normalise_citation(citation) != key:
                    continue
                position = text.find(citation)
                if position < 0 or position >= body_end:
                    continue
                cases.append({
                    "id": f"{citing.split(':')[-1]}-{cited.split(':')[-1]}",
                    "citing": citing,
                    "cited": cited,
                    "cited_title": (cited_title or "")[:70],
                    "passage": " ".join(context.split()),
                    "expected": treatment,
                })
                break
    finally:
        driver.close()
        conn.close()

    random.Random(args.seed).shuffle(cases)
    cases = cases[: args.limit]
    with open(args.out, "w") as handle:
        json.dump(cases, handle, indent=1)

    counts: dict[str, int] = {}
    for case in cases:
        counts[case["expected"]] = counts.get(case["expected"], 0) + 1
    print(f"{len(cases)} cases -> {args.out}")
    for label, n in sorted(counts.items(), key=lambda kv: -kv[1]):
        print(f"  {label:14} {n}")


if __name__ == "__main__":
    main()
