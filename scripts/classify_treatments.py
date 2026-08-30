# scripts/classify_treatments.py
"""Classify how each citing judgment treated the case it cites.

Run: .venv/bin/python -m scripts.classify_treatments [--limit N]

Writes `treatment` onto CITES edges, which is what makes "is this still good
law" answerable. Without it every edge is untreated and good_law returns
NOT_CHECKED for the whole corpus -- correct, but useless.

Resumable and incremental: edges that already carry a treatment are skipped,
so a run interrupted by quota picks up where it stopped. `--limit` bounds the
number of model calls, because the free tier is the constraint here and not
the corpus.

Only CITES.treatment is written. Nodes, CITES_SECTION and DECIDED_BY are
untouched.
"""

from __future__ import annotations

import argparse

from legal_ai.agents.treatment import BATCH_SIZE, Treatment, classify_treatments
from legal_ai.graphdb.client import get_driver
from legal_ai.ingestion.citations import extract_citation_contexts, normalise_citation
from legal_ai.knowledge.static.db import get_connection


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=50, help="model calls to spend")
    args = parser.parse_args()

    driver = get_driver()
    conn = get_connection()
    try:
        with driver.session() as session:
            pending = session.run(
                """
                MATCH (a:Judgment)-[r:CITES]->(b:Judgment)
                WHERE r.treatment IS NULL AND b.citation_key IS NOT NULL
                RETURN a.document_id AS citing, b.document_id AS cited,
                       b.citation_key AS cited_key
                """
            ).values()
        print(f"{len(pending)} untreated edges")
        if not pending:
            return

        # Group by citing judgment: its text is read once and may carry the
        # context for several of its citations.
        by_citing: dict[str, list[tuple[str, str]]] = {}
        for citing, cited, cited_key in pending:
            by_citing.setdefault(citing, []).append((cited, cited_key))

        # Batch ACROSS citing judgments, not within one. Measured
        # 2026-08-29: grouping per judgment averaged 1.4 edges a call,
        # because most citing judgments cite only one or two cases the
        # corpus also holds -- 3,424 edges would have cost ~2,400 calls
        # against a free-tier quota. Filling each batch from whatever
        # judgments it takes costs the same calls per edge as the ideal.
        calls = written = 0
        counts: dict[str, int] = {}
        batch: list[tuple[str, str, str]] = []  # (citing, cited, context)

        def flush() -> None:
            nonlocal calls, written, batch
            if not batch:
                return
            findings = classify_treatments([(cited, context) for _c, cited, context in batch])
            calls += 1
            with driver.session() as session:
                for (citing_id, cited, _context), finding in zip(batch, findings):
                    if finding.treatment is Treatment.NOT_CHECKED:
                        continue
                    session.run(
                        """
                        MATCH (a:Judgment {document_id: $citing})
                              -[r:CITES]->
                              (b:Judgment {document_id: $cited})
                        SET r.treatment = $treatment, r.treatment_why = $why
                        """,
                        citing=citing_id, cited=cited,
                        treatment=finding.treatment.value, why=finding.why,
                    )
                    written += 1
                    counts[finding.treatment.value] = counts.get(finding.treatment.value, 0) + 1
            print(f"  {calls} calls, {written} edges treated", flush=True)
            batch = []

        for citing, targets in by_citing.items():
            if calls >= args.limit:
                break
            row = conn.execute(
                "SELECT full_text FROM documents WHERE document_id = %s", (citing,)
            ).fetchone()
            # End the read transaction before the model call. Postgres holds
            # the row lock until commit, and a batch takes minutes; leaving
            # it open let a concurrent ingest's ALTER TABLE queue behind this
            # read, and every later reader queue behind the ALTER.
            conn.commit()
            if not row or not row[0]:
                continue

            by_key: dict[str, str] = {}
            for citation, context in extract_citation_contexts(row[0]):
                # Last occurrence wins: a court often notes a case early and
                # disposes of it late, and the later passage is the holding.
                by_key[normalise_citation(citation)] = context

            for cited, cited_key in targets:
                if cited_key in by_key:
                    batch.append((citing, cited, by_key[cited_key]))
                    if len(batch) >= BATCH_SIZE:
                        flush()
                        if calls >= args.limit:
                            break
        if calls < args.limit:
            flush()
    finally:
        driver.close()
        conn.close()

    print(f"model calls  : {calls}")
    print(f"edges treated: {written}")
    for treatment, n in sorted(counts.items(), key=lambda kv: -kv[1]):
        print(f"  {treatment:14} {n}")


if __name__ == "__main__":
    main()
