# scripts/classify_treatments.py
"""Classify how each citing judgment treated the case it cites.

Run: .venv/bin/python -m scripts.classify_treatments [--limit N]

Writes `treatment` onto CITES edges, which is what makes "is this still good
law" answerable. Without it every edge is untreated and good_law returns
NOT_CHECKED for the whole corpus -- correct, but useless.

The pass itself is `graphdb.treatment.classify_untreated`, which
scripts/ingest_judgments.py also runs at the end of an ingest so newly
stored judgments do not sit untreated. This stays as the way to run it
against the whole corpus, or to spend a bounded number of calls by hand.

Resumable and incremental: edges that already carry a treatment are skipped,
so a run interrupted by quota picks up where it stopped. `--limit` bounds the
number of model calls, because the free tier is the constraint here and not
the corpus.

Only CITES.treatment is written. Nodes, CITES_SECTION and DECIDED_BY are
untouched.
"""

from __future__ import annotations

import argparse

from legal_ai.graphdb.client import get_driver
from legal_ai.graphdb.treatment import Result, classify_untreated
from legal_ai.knowledge.static.db import get_connection


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=50, help="model calls to spend")
    args = parser.parse_args()

    def progress(result: Result) -> None:
        print(f"  {result.calls} calls, {result.written} edges treated", flush=True)

    driver = get_driver()
    conn = get_connection()
    try:
        result = classify_untreated(driver, conn, limit=args.limit, on_batch=progress)
    finally:
        driver.close()
        conn.close()

    print(f"model calls  : {result.calls}")
    print(f"edges treated: {result.written}")
    for treatment, n in sorted(result.counts.items(), key=lambda kv: -kv[1]):
        print(f"  {treatment:14} {n}")


if __name__ == "__main__":
    main()
