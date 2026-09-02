"""Re-embed chunk vectors with the document title prepended.

`search_vector` has always covered titles (it is generated from
title || full_text) but the vector index never did: measured 2026-09-01,
93% of sections had no part of their title in any chunk, so the section
titled "Dishonour of cheque for insufficiency, etc., of funds" could not be
retrieved by that phrase. Prepending the title to the embedded text moved
it from MISS to rank 2.

The title is embedded, not stored: the passage shown to the model is
unchanged, so this rewrites vectors only.

Sections only. Judgments are 345,761 chunks against 17,867 -- 20 hours
against one -- and a case name is usually already in the body text.

Resumable: re-running continues where an interrupted run stopped, because
progress is a row in `reembed_title_progress`, not a counter in memory.
"""

from __future__ import annotations

import argparse
import time

from legal_ai.knowledge.static.db import get_connection
from legal_ai.knowledge.static.embeddings import embed_many, model_name

BATCH = 64


def _ensure_progress_table(conn) -> None:
    exists = conn.execute(
        "SELECT 1 FROM information_schema.tables WHERE table_name = %s",
        ("reembed_title_progress",),
    ).fetchone()
    if exists:
        return
    conn.execute(
        "CREATE TABLE reembed_title_progress ("
        "chunk_id TEXT PRIMARY KEY, done_at TIMESTAMPTZ NOT NULL DEFAULT now())"
    )
    conn.commit()


def _pending(conn, limit: int) -> list[tuple[str, str, str]]:
    return conn.execute(
        """
        SELECT ch.chunk_id, ch.text, coalesce(d.title, '')
        FROM document_chunks ch
        JOIN documents d USING (document_id)
        WHERE d.document_type = 'section'
          AND coalesce(d.title, '') <> ''
          AND NOT EXISTS (
            SELECT 1 FROM reembed_title_progress p WHERE p.chunk_id = ch.chunk_id
          )
        ORDER BY ch.chunk_id
        LIMIT %s
        """,
        (limit,),
    ).fetchall()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None, help="stop after N chunks")
    args = parser.parse_args()

    conn = get_connection()
    _ensure_progress_table(conn)

    total = conn.execute(
        """SELECT count(*) FROM document_chunks ch JOIN documents d USING (document_id)
           WHERE d.document_type = 'section' AND coalesce(d.title, '') <> ''"""
    ).fetchone()[0]
    print(f"model={model_name()} | {total} section chunks", flush=True)

    done = 0
    started = time.time()
    while True:
        rows = _pending(conn, BATCH)
        if not rows:
            break
        # Read, then release, then embed. Holding the transaction across the
        # model call is what froze every reader three times -- CLAUDE.md §8.
        conn.commit()

        vectors = embed_many([f"{title}\n{text}" for _cid, text, title in rows])

        for (chunk_id, _text, _title), vector in zip(rows, vectors):
            conn.execute(
                "UPDATE document_chunks SET embedding = %s WHERE chunk_id = %s",
                (str(vector), chunk_id),
            )
            conn.execute(
                "INSERT INTO reembed_title_progress (chunk_id) VALUES (%s) "
                "ON CONFLICT DO NOTHING",
                (chunk_id,),
            )
        conn.commit()

        done += len(rows)
        rate = done / max(time.time() - started, 1e-9)
        print(f"  {done}/{total}  {rate:.1f} chunks/s", flush=True)
        if args.limit and done >= args.limit:
            break

    print(f"done: {done} chunks in {time.time() - started:.0f}s", flush=True)


if __name__ == "__main__":
    main()
