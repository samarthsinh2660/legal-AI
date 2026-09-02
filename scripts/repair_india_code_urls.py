# scripts/repair_india_code_urls.py
"""Repoint stored India Code provenance URLs at indiacode.gov.in.

The old host renumbered every handle when it migrated, so all 860 Act and
35,588 section URLs 404. The new site's DSpace REST index carries a stable
`dc.identifier.act_id` per Act and a `dc.identifier.section_number` per
section, so (act_id, section_number) identifies a section handle exactly.

Two mapping strategies were measured on 2026-09-02. Resolving each of our
Acts and then listing its sections costs ~1.4 requests per Act at 5-8s of
server latency each -- about 3 hours. One sweep of every central SECTION
item costs 354 requests, under two hours, and its coverage is checkable:
the sweep is complete only when it collects all 35,359 handles the index
reports (it did). Deep paging was verified stable (pages 0/150/353 returned
identical sets on repeat). The sweep won. Per-section title search was
never a candidate -- "Definitions" titles hundreds of sections.

A page is ~1.1MB because every section carries its own text, so the sweep
is bandwidth-bound: 54s a page serially, 4-7s a page with several requests
in flight and no sign of throttling. Hence the small thread pool.

Matching is exact on the normalised Act title, with no fuzzy fallback: a
wrong handle on a legal citation is worse than the withheld link we have
today, which is why `draft.py` withholds them at all. An Act that does not
match keeps its dead URL and stays withheld.

Two phases, never interleaved: `fetch` writes the handle index to disk,
`apply` writes the database. Nothing holds a transaction across a network
call (CLAUDE.md §8), and both phases resume from what is on disk.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from legal_ai.sources.http import polite_get

# The new site returns 502 to our own ingestion agent; a browser UA gets 200.
BROWSER_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)
SEARCH_URL = "https://indiacode.gov.in/server/api/discover/search/objects"
HANDLE_URL = "https://indiacode.gov.in/handle/{handle}"

ACT_QUERY = "dc.identifier.collection:ACT AND dc.identifier.state_name:CENTRAL"
SECTION_QUERY = "dc.identifier.collection:SECTION AND dc.identifier.state_name:CENTRAL"

CACHE = Path(__file__).resolve().parents[1] / "data" / "india_code_handles"
ACT_INDEX = CACHE / "central_acts.json"
SECTION_INDEX = CACHE / "central_sections.jsonl"

DEAD_HOST = "indiacode.nic.in"
# Both hosts, so a rerun can upgrade a row already repaired to its Act's
# handle once the sweep has reached that Act's sections. Sections sourced
# from elsewhere (a few PRS bill PDFs) are left alone by it.
ANY_INDIA_CODE = "indiacode."


WORKERS = 8


def _page(query: str, page: int) -> dict:
    response = polite_get(
        SEARCH_URL,
        params={"query": query, "size": 100, "page": page},
        headers={"User-Agent": BROWSER_UA},
        timeout=60,
    )
    response.raise_for_status()
    return response.json()["_embedded"]["searchResult"]


def _rows(body: dict) -> list[dict]:
    rows = []
    for entry in body["_embedded"]["objects"]:
        obj = entry["_embedded"]["indexableObject"]
        meta = {k: v[0]["value"] for k, v in obj["metadata"].items() if v}
        rows.append({
            "name": obj["name"],
            "handle": obj["handle"],
            "act_id": meta.get("dc.identifier.act_id"),
            "section_number": meta.get("dc.identifier.section_number"),
        })
    return rows


def normalise(title: str) -> str:
    title = title.lower().replace("’", "'").replace("\xa0", " ")
    return re.sub(r"^the ", "", re.sub(r"[^a-z0-9]+", " ", title).strip())


def normalise_section(number: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", number.upper())


def fetch(_: psycopg.Connection) -> None:
    CACHE.mkdir(parents=True, exist_ok=True)

    if not ACT_INDEX.exists():
        acts, page = [], 0
        while True:
            body = _page(ACT_QUERY, page)
            acts.extend(_rows(body))
            page += 1
            if page >= body["page"]["totalPages"]:
                break
        ACT_INDEX.write_text(json.dumps(acts, indent=1))
    print(f"central Acts indexed: {len(json.loads(ACT_INDEX.read_text()))}", file=sys.stderr)

    # Resume at the page after the last one written; a page is only recorded
    # once its rows are flushed, so a killed run repeats at most one page.
    done = 0
    if SECTION_INDEX.exists():
        for line in SECTION_INDEX.open():
            done = max(done, json.loads(line)["page"] + 1)

    body = _page(SECTION_QUERY, done)
    total_pages, expected = body["page"]["totalPages"], body["page"]["totalElements"]

    def collect(page: int) -> tuple[int, list[dict]]:
        return page, _rows(_page(SECTION_QUERY, page))

    with SECTION_INDEX.open("a") as sink, ThreadPoolExecutor(WORKERS) as pool:
        sink.write(json.dumps({"page": done, "rows": _rows(body)}) + "\n")
        for page, rows in pool.map(collect, range(done + 1, total_pages)):
            sink.write(json.dumps({"page": page, "rows": rows}) + "\n")
            sink.flush()
            if page % 20 == 0:
                print(f"sections page {page}/{total_pages}", file=sys.stderr)

    handles = {row["handle"] for line in SECTION_INDEX.open() for row in json.loads(line)["rows"]}
    print(f"section handles collected: {len(handles)} of {expected}", file=sys.stderr)
    if len(handles) != expected:
        sys.exit("incomplete sweep -- rerun before applying")


def _load() -> tuple[dict[str, list[dict]], dict[str, dict[str, str]]]:
    by_title: dict[str, list[dict]] = {}
    for act in json.loads(ACT_INDEX.read_text()):
        by_title.setdefault(normalise(act["name"]), []).append(act)

    by_act: dict[str, dict[str, str]] = {}
    for line in SECTION_INDEX.open():
        for row in json.loads(line)["rows"]:
            if row["act_id"] and row["section_number"]:
                by_act.setdefault(row["act_id"], {})[normalise_section(row["section_number"])] = row["handle"]
    return by_title, by_act


def apply(connection: psycopg.Connection) -> None:
    by_title, by_act = _load()

    with connection.cursor() as cur:
        cur.execute(
            """
            select document_id, title from documents
             where document_type = 'act'
               and provenance->'source'->>'url' like %s
               and document_id not like 'act:ipc%%'
               and document_id not like 'act:crpc%%'
             order by document_id
            """,
            (f"%{ANY_INDIA_CODE}%",),
        )
        ours = cur.fetchall()

    acts_ok = sections_ok = sections_to_act = 0
    unmatched: list[tuple[str, str, str]] = []

    for document_id, title in ours:
        candidates = by_title.get(normalise(title or ""), [])
        if len(candidates) != 1:
            unmatched.append((document_id, title or "", "ambiguous" if candidates else "no exact title match"))
            continue
        act = candidates[0]
        act_url = HANDLE_URL.format(handle=act["handle"])
        sections = by_act.get(act["act_id"], {})

        with connection.cursor() as cur:
            cur.execute(
                """
                update documents
                   set provenance = jsonb_set(provenance, '{source,url}', to_jsonb(%s::text))
                 where document_id = %s and provenance->'source'->>'url' like %s
                """,
                (act_url, document_id, f"%{DEAD_HOST}%"),
            )
            acts_ok += 1

            cur.execute(
                """
                select document_id, provenance->'source'->>'url' from documents
                 where act_id = %s and document_type = 'section'
                   and provenance->'source'->>'url' like %s
                """,
                (document_id, f"%{ANY_INDIA_CODE}%"),
            )
            for section_id, current in cur.fetchall():
                handle = sections.get(normalise_section(section_id.split(":sec-", 1)[1]))
                if handle:
                    url = HANDLE_URL.format(handle=handle)
                    sections_ok += 1
                elif DEAD_HOST in current:
                    # No section handle for this one; its Act's page is the
                    # granularity we stored before the migration anyway.
                    url = act_url
                    sections_to_act += 1
                else:
                    sections_to_act += 1
                    continue
                cur.execute(
                    """
                    update documents
                       set provenance = jsonb_set(provenance, '{source,url}', to_jsonb(%s::text))
                     where document_id = %s
                    """,
                    (url, section_id),
                )
        connection.commit()

    for row in unmatched:
        print("UNMATCHED\t" + "\t".join(row))
    print(f"Acts repaired: {acts_ok} of {len(ours)}")
    print(f"sections given their own handle: {sections_ok}")
    print(f"sections fallen back to their Act's handle: {sections_to_act}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=("fetch", "apply"))
    args = parser.parse_args()
    with psycopg.connect(os.environ["DATABASE_URL"]) as connection:
        (fetch if args.phase == "fetch" else apply)(connection)


if __name__ == "__main__":
    main()
