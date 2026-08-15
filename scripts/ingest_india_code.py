# scripts/ingest_india_code.py
"""Ingest all real India Code Acts into Postgres + Neo4j.

Run: .venv/bin/python -m scripts.ingest_india_code
"""

from __future__ import annotations

from legal_ai.ingestion.india_code.scraper import list_act_urls
from legal_ai.ingestion.pipeline import ingest_india_code


def main() -> None:
    print("Listing all India Code Central Acts...")
    urls = list_act_urls()
    print(f"Found {len(urls)} Acts. Ingesting...")

    report = ingest_india_code(act_urls=urls)

    print(f"Acts processed: {report.acts_processed}")
    print(f"Sections processed: {report.sections_processed}")
    print(f"Verification passed: {report.verification.passed}")
    print(f"Store writes: {report.store_writes}")
    if report.verification.notes:
        print("Notes:")
        for note in report.verification.notes:
            print(f"  - {note}")
    if not report.verification.passed:
        print(f"Failed document IDs: {report.verification.failed_document_ids}")


if __name__ == "__main__":
    main()
