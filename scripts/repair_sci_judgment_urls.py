# scripts/repair_sci_judgment_urls.py
"""Repoint stored Supreme Court judgment provenance at the per-document PDF.

Every SC judgment was ingested with `provenance.source.url` pointing at its
year's bundled tar, because `_archive_pdf_url` only ever built that URL for
SCI rows -- even though the archive gives a per-document path for SCI
exactly as it does for High Court (bharat_courts.archive.schema maps
parquet column "path" onto Judgment.pdf_path for both). Fixed at the
ingest-time function in dynamic_search.py; this repoints what was already
stored before that fix, the same way repair_india_code_urls.py repointed
statute URLs after that migration.

Two phases, never interleaved (CLAUDE.md §8): `fetch` reads the archive's
own year parquets and writes a local cnr -> path map, `apply` writes the
database from that map. No network call happens while a transaction is
open.

The join key is CNR, which is exact -- our document_id is `judgment:` plus
the lowercased CNR, so there is no fuzzy matching here at all, unlike the
India Code repair.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from legal_ai.knowledge.static.db import get_connection

CACHE = Path(__file__).resolve().parent / "sci_pdf_paths.json"

SCI_BUCKET = "indian-supreme-court-judgments"
REGION = "ap-south-1"


def fetch(year_from: int, year_to: int) -> None:
    """Read the archive's own year parquets; write {cnr: [path, year]} to disk."""
    import duckdb

    con = duckdb.connect()
    con.execute("INSTALL httpfs; LOAD httpfs;")

    mapping: dict[str, list] = {}
    if CACHE.exists():
        mapping = json.loads(CACHE.read_text())

    for year in range(year_from, year_to + 1):
        if any(v[1] == year for v in mapping.values()):
            continue  # resumable: a year already collected is not re-fetched
        url = f"s3://{SCI_BUCKET}/metadata/parquet/year={year}/metadata.parquet"
        try:
            rows = con.execute(
                "SELECT cnr, path FROM read_parquet(?) WHERE path IS NOT NULL", [url]
            ).fetchall()
        except Exception as exc:
            print(f"{year}: no parquet ({type(exc).__name__})", flush=True)
            continue
        for cnr, path in rows:
            mapping[cnr.lower()] = [path, year]
        print(f"{year}: {len(rows)} rows", flush=True)
        CACHE.write_text(json.dumps(mapping))

    print(f"done: {len(mapping)} judgments mapped, cached at {CACHE}", flush=True)


def _url_for(path: str, year: int) -> str:
    return (
        f"https://{SCI_BUCKET}.s3.{REGION}.amazonaws.com"
        f"/data/pdf/year={year}/english/{path}_EN.pdf"
    )


def apply() -> None:
    """Repoint every stored SC judgment whose CNR is in the cached map."""
    mapping = json.loads(CACHE.read_text())

    conn = get_connection()
    rows = conn.execute(
        "SELECT document_id, provenance FROM documents "
        "WHERE document_type = 'judgment' AND document_id LIKE 'judgment:escr%'"
    ).fetchall()
    print(f"{len(rows)} stored SC judgments", flush=True)

    updated = skipped = 0
    for document_id, provenance in rows:
        cnr = document_id.removeprefix("judgment:")
        found = mapping.get(cnr)
        if found is None:
            skipped += 1
            continue
        path, year = found
        provenance["source"]["url"] = _url_for(path, year)
        provenance["source"]["name"] = (
            "Bharat Courts archive (Vanga public AWS Open Data, direct PDF)"
        )
        conn.execute(
            "UPDATE documents SET provenance = %s WHERE document_id = %s",
            (psycopg.types.json.Json(provenance), document_id),
        )
        updated += 1

    conn.commit()
    conn.close()
    print(f"done: {updated} repointed, {skipped} had no CNR in the map", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=["fetch", "apply"])
    parser.add_argument("--from-year", type=int, default=1999)
    parser.add_argument("--to-year", type=int, default=2026)
    args = parser.parse_args()

    if args.phase == "fetch":
        fetch(args.from_year, args.to_year)
    else:
        apply()


if __name__ == "__main__":
    main()
