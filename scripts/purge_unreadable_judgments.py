# scripts/purge_unreadable_judgments.py
"""Remove stored judgments whose text the ingest gate would now refuse.

Run: .venv/bin/python -m scripts.purge_unreadable_judgments --dry-run
     .venv/bin/python -m scripts.purge_unreadable_judgments --apply

Some PDFs have a broken font encoding map and extract as mojibake --
`!" #$%$ &'())` -- rather than failing outright. The old gate tested only
length, so these were stored, embedded and chunked, and now compete for
slots in every vector search against real judgments.

Selection uses `_text_check`, the same predicate the gate applies to new
documents, so what is deleted is exactly what would be refused today. It is
deliberately not a second, separate rule that could drift away from it.

Judgments only. Sections and Acts are never selected, read, or written.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from legal_ai.graphdb.client import get_driver
from legal_ai.ingestion.judgments.dynamic_search import _text_check
from legal_ai.knowledge.static.db import get_connection


class _TextOnly:
    """_text_check reads one field; this avoids rebuilding whole documents."""

    def __init__(self, full_text: str) -> None:
        self.full_text = full_text


def main() -> None:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    parser.add_argument("--report", default="purge_report.json")
    args = parser.parse_args()

    conn = get_connection()
    rows = conn.execute(
        "SELECT document_id, title, full_text FROM documents "
        "WHERE document_type = 'judgment'"
    ).fetchall()

    doomed = []
    for doc_id, title, text in rows:
        if not _text_check(_TextOnly(text)):
            doomed.append({
                "document_id": doc_id,
                "title": (title or "")[:120],
                "chars": len(text),
                "alpha_ratio": round(
                    sum(1 for c in text.strip() if c.isalpha()) / max(len(text.strip()), 1), 3
                ),
                "sample": re.sub(r"\s+", " ", text)[:160],
            })

    report = Path(args.report)
    report.write_text(json.dumps({
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "judgments_examined": len(rows),
        "selected_for_deletion": len(doomed),
        "applied": args.apply,
        "documents": doomed,
    }, indent=2))

    print(f"judgments examined  : {len(rows)}")
    print(f"would delete        : {len(doomed)}")
    print(f"would keep          : {len(rows) - len(doomed)}")
    print(f"report written      : {report}")

    if not doomed:
        conn.close()
        return

    worst = min(doomed, key=lambda d: d["alpha_ratio"])
    best = max(doomed, key=lambda d: d["alpha_ratio"])
    print(f"  alpha_ratio range : {worst['alpha_ratio']} .. {best['alpha_ratio']}")
    print(f"  largest           : {max(d['chars'] for d in doomed)} chars")
    print("  highest-alpha selected document (the closest call):")
    print(f"    {best['document_id']}  {best['sample'][:100]!r}")

    if not args.apply:
        print("\ndry run -- nothing deleted. Re-run with --apply.")
        conn.close()
        return

    ids = [d["document_id"] for d in doomed]
    with conn.cursor() as cur:
        cur.execute("DELETE FROM document_chunks WHERE document_id = ANY(%s)", (ids,))
        chunks = cur.rowcount
        cur.execute(
            "DELETE FROM documents WHERE document_id = ANY(%s) "
            "AND document_type = 'judgment'",
            (ids,),
        )
        docs = cur.rowcount
    conn.commit()

    # A Judgment node left behind with no document row is exactly the kind
    # of quiet inconsistency this cleanup exists to remove.
    driver = get_driver()
    try:
        with driver.session() as session:
            nodes = session.run(
                "MATCH (j:Judgment) WHERE j.document_id IN $ids "
                "DETACH DELETE j RETURN count(j) AS n",
                ids=ids,
            ).single()["n"]
    finally:
        driver.close()

    remaining = conn.execute(
        "SELECT count(*) FROM documents WHERE document_type = 'judgment'"
    ).fetchone()[0]
    conn.close()

    print(f"\ndeleted  {docs} documents, {chunks} chunks, {nodes} graph nodes")
    print(f"judgments remaining: {remaining}")


if __name__ == "__main__":
    main()
