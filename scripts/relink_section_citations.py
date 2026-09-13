# scripts/relink_section_citations.py
"""Re-resolve every judgment's section references with the current resolver.

    .venv/bin/python -m scripts.relink_section_citations --dry-run
    .venv/bin/python -m scripts.relink_section_citations

CITES_SECTION edges are written once, at ingest, by whatever
`find_act_by_name` could resolve at that moment. Two things made most of
them wrong or missing, and neither heals on its own:

- The criminal codes arrived after most judgments. "Section 106 of the
  Evidence Act" failed because the Evidence Act was not held yet, and was
  never looked at again.
- The resolver could not read an abbreviation -- 2,837 "IPC" and 1,947
  "CrPC" references were left dangling -- and it matched words as
  substrings, so "Income Tax Act" landed on the Black Money Act and "State
  Act" on the Deo Estate Act.

This recomputes each judgment's edges from its stored text and replaces
them: an edge the resolver no longer supports is removed, one it now
supports is added, and `dangling_section_citations` is rewritten rather
than appended to. `mentions` is recounted from the text as ingest does, and
it is the only property these edges carry.

Only CITES_SECTION and the dangling list are written. CITES, DECIDED_BY,
CONTAINS, treatments and every node are untouched.

Idempotent, so it resumes by running again: a judgment whose edges already
match is skipped without a write. Texts are read in short batches, each its
own transaction -- a single cursor held open for the whole run is how a
bulk job once queued an ALTER TABLE behind it and froze every reader.
"""

from __future__ import annotations

import argparse
import collections
import time

from legal_ai.graphdb.client import get_driver
from legal_ai.ingestion.statute_citations import extract_section_references
from legal_ai.knowledge.static.db import get_connection
from legal_ai.knowledge.static.store import find_act_by_name

BATCH = 200

_REPLACE = """
MATCH (j:Judgment {document_id: $judgment})
OPTIONAL MATCH (j)-[old:CITES_SECTION]->(s:Section)
WHERE NOT s.document_id IN $keep
DELETE old
WITH DISTINCT j
SET j.dangling_section_citations = $dangling
WITH j
UNWIND $edges AS edge
MATCH (s:Section {document_id: edge.section})
MERGE (j)-[r:CITES_SECTION]->(s)
SET r.mentions = edge.mentions
"""


def _plan(text: str, resolve, sections: set[str]) -> tuple[dict[str, int], list[str]]:
    """The edges and dangling references this text should produce.

    One section reached through two names -- "302 IPC" and "302 of the
    Indian Penal Code" -- is one edge, and its mentions add up.
    """
    edges: dict[str, int] = {}
    dangling: list[str] = []
    for ref in extract_section_references(text):
        act = resolve(ref.act_name, ref.act_year)
        section = f"{act}:sec-{ref.section_number}" if act else None
        if section in sections:
            edges[section] = edges.get(section, 0) + ref.mentions
        else:
            dangling.append(ref.raw)
    return edges, sorted(set(dangling))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="report, write nothing")
    parser.add_argument("--limit", type=int, default=0, help="judgments this run")
    args = parser.parse_args()

    conn = get_connection()
    driver = get_driver()
    try:
        sections = {row[0] for row in conn.execute(
            "SELECT document_id FROM documents WHERE document_type = 'section'"
        ).fetchall()}
        judgments = [row[0] for row in conn.execute(
            "SELECT document_id FROM documents WHERE document_type = 'judgment' "
            "AND full_text IS NOT NULL ORDER BY document_id"
        ).fetchall()]
        conn.commit()
        if args.limit:
            judgments = judgments[: args.limit]

        with driver.session() as session:
            current: dict[str, dict[str, int]] = collections.defaultdict(dict)
            for judgment, section, mentions in session.run(
                "MATCH (j:Judgment)-[r:CITES_SECTION]->(s:Section) "
                "RETURN j.document_id, s.document_id, r.mentions"
            ).values():
                current[judgment][section] = mentions
            dangling_now = dict(session.run(
                "MATCH (j:Judgment) WHERE j.dangling_section_citations IS NOT NULL "
                "RETURN j.document_id, j.dangling_section_citations"
            ).values())
            in_graph = {row[0] for row in session.run(
                "MATCH (j:Judgment) RETURN j.document_id"
            ).values()}

        cache: dict[tuple[str, str | None], str | None] = {}

        def resolve(name: str, year: str | None) -> str | None:
            key = (name, year)
            if key not in cache:
                cache[key] = find_act_by_name(conn, name, year)
                conn.commit()
            return cache[key]

        tally = collections.Counter()
        started = time.perf_counter()
        for start in range(0, len(judgments), BATCH):
            ids = judgments[start : start + BATCH]
            texts = conn.execute(
                "SELECT document_id, full_text FROM documents WHERE document_id = ANY(%s)",
                (ids,),
            ).fetchall()
            conn.commit()

            for judgment, text in texts:
                # A judgment stored but never written to the graph has no node
                # to hang an edge on. Creating one here would give it
                # CITES_SECTION and none of its CITES or DECIDED_BY -- a partial
                # node that reads as complete. Ingest writes judgment nodes.
                if judgment not in in_graph:
                    tally["judgments not in graph"] += 1
                    continue
                edges, dangling = _plan(text or "", resolve, sections)
                before = current.get(judgment, {})
                tally["edges before"] += len(before)
                tally["edges after"] += len(edges)
                tally["edges kept"] += len(before.keys() & edges.keys())
                tally["edges added"] += len(edges.keys() - before.keys())
                tally["edges removed"] += len(before.keys() - edges.keys())
                tally["dangling after"] += len(dangling)

                unchanged = before == edges and sorted(dangling_now.get(judgment) or []) == dangling
                if unchanged or args.dry_run:
                    continue
                with driver.session() as session:
                    session.run(
                        _REPLACE, judgment=judgment, keep=list(edges), dangling=dangling,
                        edges=[{"section": s, "mentions": m} for s, m in edges.items()],
                    ).consume()
                tally["judgments rewritten"] += 1

            done = min(start + BATCH, len(judgments))
            rate = done / (time.perf_counter() - started)
            print(f"  {done}/{len(judgments)} judgments  {rate:.0f}/s", flush=True)
    finally:
        driver.close()
        conn.close()

    mode = "DRY RUN -- nothing written" if args.dry_run else "applied"
    print(f"\n{mode}")
    for key in ("edges before", "edges after", "edges kept", "edges added",
                "edges removed", "dangling after", "judgments rewritten",
                "judgments not in graph"):
        print(f"  {key:22} {tally[key]:>7}")


if __name__ == "__main__":
    main()
