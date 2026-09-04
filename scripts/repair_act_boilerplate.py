# scripts/repair_act_boilerplate.py
"""Strip the India Code page furniture out of stored Act documents.

Run: .venv/bin/python -m scripts.repair_act_boilerplate            # report only
     .venv/bin/python -m scripts.repair_act_boilerplate --apply    # write

845 of the 863 `document_type='act'` rows hold the India Code *web page*
rather than the Act: a navigation sidebar, the full list of Indian states,
a language switcher, then -- after the part worth keeping -- a run of empty
dialog templates and the site footer. Measured 2026-09-04.

The middle of each page is real and worth keeping: the Act's metadata (act
number, enactment date, long title, ministry) and its full section index,
"Section 138. Dishonour of cheque for insufficiency, etc., of funds in the
account." That index is the one thing these rows contribute that the
per-section documents do not.

Two reasons this is worth repairing rather than deleting:

  - The header lists every state in India. Any question naming a state can
    match all 845 of these rows on those tokens alone, and they are titled
    with the Act's real name, so they look authoritative.
  - Retrieval measured them at 2 of 500 top-10 slots across the 50-question
    benchmark, so this is corpus hygiene, not a ranking fix. It was
    mis-diagnosed as the cause of a retrieval bug once already; the numbers
    are in docs/QA_cases_2026_09_04.md.

Deterministic, not a model: the page is machine-generated, so the content
sits between two fixed markers. Verified against all 845 rows -- every one
carries both, in order.

`search_vector` is a generated column and refreshes itself. `embedding` is
not: it is stored, and would otherwise keep describing the boilerplate, so
each repaired row is re-embedded from its cleaned text. The embedding call
happens with no transaction open (CLAUDE.md section 8).

Safe to re-run. A cleaned row no longer matches the boilerplate marker, so
an interrupted run resumes exactly where it stopped.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from legal_ai.knowledge.static.db import get_connection
from legal_ai.knowledge.static.embeddings import embed_many

# The scrape marker. Present in every affected row and in none of the 18
# act rows that hold real text, which is what makes it the selector.
MARKER = "Screen Reader Access"

# Real content opens at the Act's own metadata block.
HEAD = "Act ID:"

# ...and ends at the first of the trailing dialog templates. Three spellings
# because the page emits whichever its content requires; the earliest wins.
TAILS = ("Show All Sections Previous", "× Act Name", "Download India Code Logo")

SELECT = (
    "SELECT document_id, full_text FROM documents "
    "WHERE document_type = 'act' AND full_text LIKE %s "
    "ORDER BY document_id LIMIT %s"
)
LIKE = f"%{MARKER}%"


def clean(text: str) -> str | None:
    """`text` between the markers, or None if it is not the expected shape.

    None rather than a guess: a page that does not carry both markers is not
    the page this was written for, and truncating it on a hunch would lose
    text no other row holds.
    """
    start = text.find(HEAD)
    if start == -1:
        return None
    ends = [position for position in (text.find(tail) for tail in TAILS) if position != -1]
    end = min(ends) if ends else -1
    if end == -1 or end <= start:
        return None
    return text[start:end].strip()


def run(apply: bool, batch_size: int, limit: int | None = None) -> None:
    conn = get_connection()
    total = conn.execute(
        "SELECT count(*) FROM documents WHERE document_type = 'act' AND full_text LIKE %s",
        (LIKE,),
    ).fetchone()[0]
    print(f"{total} act documents carry page furniture", flush=True)

    if not apply:
        rows = conn.execute(SELECT, (LIKE, total or 1)).fetchall()
        repairable = [(d, t, clean(t)) for d, t in rows]
        unshaped = [d for d, _t, c in repairable if c is None]
        kept = [(len(t), len(c)) for _d, t, c in repairable if c is not None]
        print(f"repairable      : {len(kept)}")
        print(f"unexpected shape: {len(unshaped)}" + (f" {unshaped[:5]}" if unshaped else ""))
        if kept:
            before = sum(a for a, _ in kept)
            after = sum(b for _, b in kept)
            print(f"characters      : {before:,} -> {after:,} ({after / before:.0%} kept)")
        print("\nnothing written; pass --apply to write", flush=True)
        conn.close()
        return

    repaired = skipped = 0
    while True:
        if limit is not None and repaired >= limit:
            break
        size = batch_size if limit is None else min(batch_size, limit - repaired)
        # Read, then release: the embedding call below must not run with a
        # transaction open.
        rows = conn.execute(SELECT, (LIKE, size)).fetchall()
        conn.commit()
        if not rows:
            break

        work = []
        for document_id, text in rows:
            cleaned = clean(text)
            if cleaned is None:
                skipped += 1
                continue
            work.append((document_id, cleaned))
        if not work:
            print(f"{skipped} rows did not match the expected shape; stopping", flush=True)
            break

        vectors = embed_many([text for _document_id, text in work])

        for (document_id, cleaned), vector in zip(work, vectors):
            conn.execute(
                "UPDATE documents SET full_text = %s, embedding = %s WHERE document_id = %s",
                (cleaned, vector, document_id),
            )
        conn.commit()
        repaired += len(work)
        print(f"  {repaired}/{total}", flush=True)

    conn.close()
    print(f"done: {repaired} repaired, {skipped} left alone", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="write; default reports only")
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument(
        "--limit", type=int, default=None,
        help="stop after this many rows; for proving a run before the whole corpus",
    )
    args = parser.parse_args()
    run(apply=args.apply, batch_size=args.batch_size, limit=args.limit)


if __name__ == "__main__":
    main()
