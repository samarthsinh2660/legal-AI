# scripts/ingest_judgments_by_judge.py
"""Grow the judgment corpus: pull by judge from the Bharat Courts archive.

Run: .venv/bin/python -m scripts.ingest_judgments_by_judge

Why by judge rather than by party or subject: the archive index has no
subject column, and party search only finds a case you can already name.
The judge field is the one high-recall axis the index actually supports,
and a judge's decade of judgments is a connected body of law -- they cite
each other and cite the same sections, which is what a precedent graph
needs and what 18 unconnected judgments cannot give.

Resumable. store_judgment() upserts on content_hash, so re-running skips
what is already stored rather than re-embedding it.
"""

from __future__ import annotations

import argparse
import asyncio
import io
import time

import pypdf

from legal_ai.ingestion.judgments.dynamic_search import _to_canonical, _verify
from legal_ai.ingestion.judgments.store import store_judgment

# Five judges per court, chosen for sitting span across 2016-2026 so the
# range is populated rather than clustered in one or two years.
SCI_JUDGES = ["CHANDRACHUD", "NARIMAN", "KHANWILKAR", "GAVAI", "SANJIV KHANNA"]
HC_JUDGES = [
    "PRATHIBA M. SINGH",
    "SANJEEV NARULA",
    "REKHA PALLI",
    "YASHWANT VARMA",
    "NAVIN CHAWLA",
]

YEARS = (2016, 2026)


async def _fetch(client, court: str, judge: str, limit: int):
    results = await client.search(court=court, judge=judge, year=YEARS, limit=limit)
    for judgment in results:
        try:
            pdf_bytes = await client.fetch_pdf(judgment)
        except Exception as exc:
            yield judgment, None, f"fetch failed: {type(exc).__name__}"
            continue
        try:
            reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
            text = "\n".join(page.extract_text() or "" for page in reader.pages)
        except Exception as exc:
            yield judgment, None, f"pdf parse failed: {type(exc).__name__}"
            continue
        # A scanned judgment with no text layer is not a failure worth
        # stopping for, but it must not be stored as an empty document.
        if not text.strip():
            yield judgment, None, "no text layer"
            continue
        yield judgment, text, None


async def ingest(court: str, judges: list[str], per_judge: int) -> dict:
    import bharat_courts as bc

    stats = {"seen": 0, "stored": 0, "unchanged": 0, "skipped": 0, "unverified": 0}
    async with bc.ArchiveClient() as client:
        for judge in judges:
            started = time.monotonic()
            before = dict(stats)
            async for judgment, text, problem in _fetch(client, court, judge, per_judge):
                stats["seen"] += 1
                if problem is not None:
                    stats["skipped"] += 1
                    continue
                doc = _to_canonical(judgment, text, judgment.title or judge)
                passed, notes = _verify([doc])
                if not passed:
                    # Same gate as India Code, no lighter bar for judgments.
                    stats["unverified"] += 1
                    print(f"    ! rejected {doc.document_id}: {'; '.join(notes[:2])}")
                    continue
                try:
                    changed = store_judgment(doc)
                except Exception as exc:
                    stats["skipped"] += 1
                    print(f"    ! store failed {doc.document_id}: {type(exc).__name__}: {exc}")
                    continue
                stats["stored" if changed else "unchanged"] += 1
            elapsed = time.monotonic() - started
            got = stats["stored"] - before["stored"]
            print(
                f"  {court}/{judge}: +{got} new, "
                f"{stats['unchanged'] - before['unchanged']} already stored, "
                f"{stats['skipped'] - before['skipped']} skipped, "
                f"{stats['unverified'] - before['unverified']} rejected "
                f"({elapsed:.0f}s)",
                flush=True,
            )
    return stats


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--per-judge", type=int, default=40)
    parser.add_argument("--hc", default="delhi", help="High Court partition code")
    args = parser.parse_args()

    overall = {}
    for court, judges in (("sci", SCI_JUDGES), (args.hc, HC_JUDGES)):
        print(f"== {court}: {len(judges)} judges, {YEARS[0]}-{YEARS[1]}, "
              f"up to {args.per_judge} each", flush=True)
        overall[court] = asyncio.run(ingest(court, judges, args.per_judge))

    print("\n== totals")
    for court, stats in overall.items():
        print(f"  {court}: {stats}")


if __name__ == "__main__":
    main()
