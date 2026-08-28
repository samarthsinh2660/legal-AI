# scripts/ingest_judgments.py
"""Grow the judgment corpus from the Bharat Courts archive.

Two modes. `--all-hc` walks every High Court partition year by year; the
default walks a named set of Supreme Court judges. Both write through the
same verification gate and store step.

Run: .venv/bin/python -m scripts.ingest_judgments --all-hc
     .venv/bin/python -m scripts.ingest_judgments            # Supreme Court by judge

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


async def ingest_court(court: str, per_year: int) -> dict:
    """`per_year` judgments from each year in YEARS, not `per_year * years`
    taken from the top.

    Measured 2026-08-27: a single search over the whole range returns
    newest-first, so `search(court="bombay", year=(2016, 2026), limit=150)`
    returned 150 documents *all dated 2026*. A range plus a limit is not a
    sample of the range -- it is the most recent slice of it, and the corpus
    it builds is a snapshot of this year wearing a decade's label.

    Querying year by year is the only way the range means what it says.
    """
    import bharat_courts as bc

    stats = {"seen": 0, "stored": 0, "unchanged": 0, "skipped": 0, "unverified": 0}
    started = time.monotonic()
    by_year: dict[int, int] = {}
    async with bc.ArchiveClient() as client:
        for year in range(YEARS[0], YEARS[1] + 1):
            # Reported per year, not only per court. A court-level line is
            # one message after 45 minutes of downloads, which makes a
            # stalled run and a slow one look identical.
            year_started = time.monotonic()
            before_stored = stats["stored"]
            async for judgment, text, problem in _fetch_court(client, court, year, per_year):
                stats["seen"] += 1
                if problem is not None:
                    stats["skipped"] += 1
                    continue
                doc = _to_canonical(judgment, text, judgment.title or court)
                passed, notes = _verify([doc])
                if not passed:
                    stats["unverified"] += 1
                    continue
                try:
                    changed = store_judgment(doc)
                except Exception as exc:
                    stats["skipped"] += 1
                    print(f"    ! store failed {doc.document_id}: {type(exc).__name__}", flush=True)
                    continue
                stats["stored" if changed else "unchanged"] += 1
                by_year[year] = by_year.get(year, 0) + 1
            print(f"    {court} {year}: +{stats['stored'] - before_stored} "
                  f"({time.monotonic() - year_started:.0f}s)", flush=True)
    span = f"{min(by_year)}-{max(by_year)}" if by_year else "none"
    print(
        f"  {court:22} +{stats['stored']:4} new, {stats['unchanged']:4} known, "
        f"{stats['skipped']:3} skipped, {stats['unverified']:3} rejected  "
        f"years {span}  ({time.monotonic() - started:.0f}s)",
        flush=True,
    )
    return stats


async def _fetch_court(client, court: str, year: int, limit: int):
    try:
        results = await client.search(court=court, year=year, limit=limit)
    except Exception as exc:
        print(f"  {court:22} {year} SEARCH FAILED {type(exc).__name__}", flush=True)
        return
    for judgment in results:
        try:
            pdf_bytes = await client.fetch_pdf(judgment)
        except Exception as exc:
            # The index lists documents whose PDFs are not in the bucket --
            # the current year especially, where metadata runs ahead of the
            # scans. Not fatal, but it must be counted, not swallowed.
            yield judgment, None, f"fetch failed: {type(exc).__name__}"
            continue
        try:
            reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
            text = "\n".join(page.extract_text() or "" for page in reader.pages)
        except Exception as exc:
            yield judgment, None, f"pdf parse failed: {type(exc).__name__}"
            continue
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
    global YEARS

    parser = argparse.ArgumentParser()
    parser.add_argument("--per-judge", type=int, default=40)
    parser.add_argument("--hc", default="delhi", help="High Court partition code")
    parser.add_argument(
        "--all-hc", action="store_true",
        help="ingest every High Court by year instead of five judges of one",
    )
    parser.add_argument("--per-year", type=int, default=15,
                        help="judgments per court per year")
    parser.add_argument("--sc", action="store_true",
                        help="ingest the Supreme Court year by year")
    parser.add_argument("--from-year", type=int, default=2016)
    parser.add_argument("--to-year", type=int, default=2026)
    args = parser.parse_args()

    YEARS = (args.from_year, args.to_year)
    overall = {}
    if args.sc:
        # The Supreme Court is the only citable court in the corpus: its
        # judgments carry SCR citations, so they can be cited BY others.
        # High Court judgments cannot (no citation column in the archive),
        # which is why depth here, not breadth there, is what the precedent
        # graph needs.
        print(f"== Supreme Court, {args.per_year}/year across "
              f"{YEARS[0]}-{YEARS[1]}", flush=True)
        overall["sci"] = asyncio.run(ingest_court("sci", args.per_year))
    elif args.all_hc:
        from bharat_courts import list_high_courts

        courts = [c.slug for c in list_high_courts()]
        print(f"== {len(courts)} High Courts, {args.per_year}/year "
              f"across {YEARS[0]}-{YEARS[1]}", flush=True)
        for court in courts:
            overall[court] = asyncio.run(ingest_court(court, args.per_year))
    else:
        for court, judges in (("sci", SCI_JUDGES), (args.hc, HC_JUDGES)):
            print(f"== {court}: {len(judges)} judges, {YEARS[0]}-{YEARS[1]}, "
                  f"up to {args.per_judge} each", flush=True)
            overall[court] = asyncio.run(ingest(court, judges, args.per_judge))

    total = {k: sum(s[k] for s in overall.values()) for k in
             ("seen", "stored", "unchanged", "skipped", "unverified")}
    print(f"\n== totals across {len(overall)} courts: {total}")


if __name__ == "__main__":
    main()
