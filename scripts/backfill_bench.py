# scripts/backfill_bench.py
"""Populate judges / bench_size for judgments already stored.

Run: .venv/bin/python -m scripts.backfill_bench

New judgments get this at ingest (see ingestion/judgments/store.py). This
pass is for the corpus stored before the columns existed, and is safe to
re-run -- it recomputes from full_text, which does not change.

Reads and writes nothing outside those two columns, so statutes and every
retrieval path are untouched.
"""

from __future__ import annotations

import json

from legal_ai.ingestion.bench import extract_bench
from legal_ai.knowledge.static.db import ensure_bench_schema, get_connection


def main() -> None:
    conn = get_connection()
    ensure_bench_schema(conn)
    rows = conn.execute(
        "SELECT document_id, court, full_text FROM documents "
        "WHERE document_type = 'judgment'"
    ).fetchall()
    print(f"{len(rows)} judgments")

    parsed = 0
    by_court: dict[str, list[int]] = {}
    for document_id, court, text in rows:
        judges = extract_bench(text)
        conn.execute(
            "UPDATE documents SET judges = %s, bench_size = %s WHERE document_id = %s",
            (json.dumps(judges) if judges else None, len(judges) or None, document_id),
        )
        if judges:
            parsed += 1
            by_court.setdefault(court or "unknown", []).append(len(judges))
    conn.commit()

    print(f"bench parsed for {parsed} ({parsed / max(len(rows), 1):.0%})")
    for court, sizes in sorted(by_court.items(), key=lambda kv: -len(kv[1]))[:6]:
        print(f"  {court:32} {len(sizes):5}  mean bench {sum(sizes)/len(sizes):.2f}")

    larger = conn.execute(
        "SELECT count(*) FROM documents WHERE bench_size >= 5"
    ).fetchone()[0]
    print(f"Constitution Benches (5+): {larger}")
    conn.close()


if __name__ == "__main__":
    main()
