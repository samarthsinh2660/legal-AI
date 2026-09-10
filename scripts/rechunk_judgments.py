# scripts/rechunk_judgments.py
"""Re-chunk judgments whose paragraph numbering the chunker used to misread.

    .venv/bin/python -m scripts.rechunk_judgments [--limit N] [--dry-run]

A year wrapped onto its own line -- "2022." -- used to read as paragraph
2022, splitting a paragraph in half and labelling the half with a year. The
label is what a pinpoint cites, so the answer could send a reader to a
paragraph the judgment does not have. `retrieval/chunking/judgment.py` no
longer treats a year as a paragraph number; this applies that to what is
already stored.

Only judgments are touched, and only those whose text actually contains such
a marker: the statute chunker never had the defect. Chunks are replaced per
document by `upsert_chunks`, which deletes and re-inserts in one
transaction, so an interrupted run leaves whole documents behind it and no
half-rewritten one.

The only thing written outside `document_chunks` is `documents.embedding`,
which `chunk_and_store` nulls because a chunked document is represented by
its chunks; for these documents it was already null. URL, provenance and
every Neo4j edge -- the citation graph and its treatments -- are untouched,
so no source link and no good-law reading moves.

Embedding is the cost: the chunks of the affected documents have to be
re-embedded. With LEGAL_AI_EMBED_URL unset the model loads in-process and
uses the GPU if there is one, which is several times faster than the CPU
containers for a job this size.

Resumable against the database rather than a progress file: a document is
done when its stored chunks already match what the current chunker
produces. That survives a reboot, which a file under /tmp did not.
"""

from __future__ import annotations

import argparse
import re
import time

from legal_ai.knowledge.static.chunk_store import DEFAULT_MAX_CHARS, chunk_and_store
from legal_ai.knowledge.static.db import get_connection
from legal_ai.retrieval.chunking.judgment import chunk_judgment

# The same line-start numbering the chunker matches, so this selects exactly
# the documents whose chunking changes.
_MARKER = re.compile(r"^[ \t]*(\d{1,4})[.)]\s+", re.MULTILINE)
_YEAR = range(1900, 2101)


def _already_done(conn, document_id: str, text: str) -> bool:
    """Whether the stored chunks are what the chunker produces now.

    Exact, and cheap: chunking is a regex split, so this costs a read and no
    model call. It is also the only test that catches the documents whose
    boundaries move without leaving a year-labelled chunk behind.
    """
    # Short enough to embed whole is never chunked -- `chunk_and_store`
    # returns before splitting. Without this, a document with no chunks by
    # design reads as one still needing them, and the run never finishes.
    if len(text) <= DEFAULT_MAX_CHARS:
        return True

    stored = conn.execute(
        "SELECT label, text FROM document_chunks WHERE document_id = %s "
        "ORDER BY ordinal", (document_id,)
    ).fetchall()
    conn.commit()
    if not stored:
        return False
    fresh = chunk_judgment(text, max_chars=DEFAULT_MAX_CHARS)
    return [(c.label, c.text) for c in fresh] == [(label, body) for label, body in stored]


def _affected(conn) -> list[tuple[str, str]]:
    rows = conn.execute(
        "SELECT document_id, full_text FROM documents "
        "WHERE document_type = 'judgment' AND full_text IS NOT NULL "
        "ORDER BY document_id"
    ).fetchall()
    conn.commit()
    return [
        (document_id, text)
        for document_id, text in rows
        if any(int(m.group(1)) in _YEAR for m in _MARKER.finditer(text or ""))
    ]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0, help="documents this run")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    conn = get_connection()
    try:
        affected = _affected(conn)
        todo = [(d, t) for d, t in affected if not _already_done(conn, d, t)]
        print(f"{len(affected)} affected, {len(affected) - len(todo)} already done, "
              f"{len(todo)} to go", flush=True)
        if args.dry_run or not todo:
            return
        if args.limit:
            todo = todo[: args.limit]

        started = time.perf_counter()
        chunks = 0
        for index, (document_id, text) in enumerate(todo, 1):
            row = conn.execute(
                "SELECT document_type, title FROM documents WHERE document_id = %s",
                (document_id,),
            ).fetchone()
            conn.commit()
            if not row:
                continue
            document_type, title = row
            chunks += chunk_and_store(conn, document_id, text, document_type, title=title)
            if index % 50 == 0 or index == len(todo):
                rate = index / (time.perf_counter() - started)
                left = (len(todo) - index) / rate / 60 if rate else 0
                print(f"  {index}/{len(todo)} documents, {chunks} chunks, "
                      f"{rate:.1f} docs/s, ~{left:.0f} min left", flush=True)
    finally:
        conn.close()

    print(f"re-chunked {len(todo)} documents into {chunks} chunks")


if __name__ == "__main__":
    main()
