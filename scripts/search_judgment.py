"""CLI for the dynamic, lazy-cached judgment search tool.

See docs/superpowers/specs/2026-08-17-dynamic-judgment-search-design.md.
Finds and verifies a real judgment (DB -> Bharat Courts archive ->
Indian Kanoon); by default also stores it on a verified pass (upsert +
embed + graph edges, including CITES_SECTION for any Act/Section
references found in the text) — pass --no-store to skip that.

Run: .venv/bin/python -m scripts.search_judgment "<case name or citation>" [--year YYYY] [--no-store]
"""

from __future__ import annotations

import argparse
import json
import sys

from legal_ai.ingestion.judgments.dynamic_search import search_judgment
from legal_ai.ingestion.judgments.store import store_judgment


def main() -> None:
    parser = argparse.ArgumentParser(description="Find, verify, and (by default) store a real judgment.")
    parser.add_argument("query", help="Case name or citation to look up.")
    parser.add_argument(
        "--year",
        type=int,
        default=None,
        help="Decision year, if known. Strongly recommended — without it, the Bharat Courts "
        "archive scans every court partition and is much slower.",
    )
    parser.add_argument(
        "--no-store",
        action="store_true",
        help="Only find and verify — don't write to Postgres/Neo4j.",
    )
    parser.add_argument(
        "--skip-db",
        dest="skip_db",
        action="store_true",
        help="Force a fresh live search even if a cached DB match exists — use when a "
        "previous cached match turned out to be the wrong document (same parties, "
        "different proceeding).",
    )
    args = parser.parse_args()

    result = search_judgment(args.query, year=args.year, skip_db=args.skip_db)

    if not result.found or result.document is None:
        print(json.dumps({"found": False, "notes": result.notes}, indent=2))
        sys.exit(1)

    doc = result.document
    stored = None
    if not args.no_store and result.source != "database" and result.verified:
        stored = store_judgment(doc)

    print(
        json.dumps(
            {
                "found": True,
                "source": result.source,
                "verified": result.verified,
                "stored": stored,
                "notes": result.notes,
                "document_id": doc.document_id,
                "title": doc.title,
                "court": doc.court,
                "citation": doc.citation,
                "case_number": doc.case_number,
                "decision_date": doc.decision_date.isoformat() if doc.decision_date else None,
                "disposal_nature": doc.disposal_nature,
                "full_text_length": len(doc.full_text),
                "source_url": doc.provenance.source.url,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
