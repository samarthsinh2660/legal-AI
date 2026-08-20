"""Chunk and embed documents too long for the embedding model to read whole.

Any document longer than the model's token limit is silently truncated, so
its tail is never searchable. This splits those documents on their own
structural boundaries, embeds each piece, and clears the parent's
document-level embedding -- a truncated whole-document vector misrepresents
the document, and leaving it would also double-count it against its chunks.

Acts are excluded: an Act's text is its sections concatenated, and the
sections are embedded individually.

Resumable by construction -- it asks the database which long documents have
no chunks yet, so an interrupted run is continued by running it again.

    .venv/bin/python -m scripts.build_chunks --limit 50   # trial run
    .venv/bin/python -m scripts.build_chunks             # everything
"""

from __future__ import annotations

import argparse
import time

from legal_ai.knowledge.static.chunk_store import chunk_and_store, documents_needing_chunks
from legal_ai.knowledge.static.db import ensure_chunk_schema, get_connection
from legal_ai.knowledge.static.embeddings import model_name

# Characters per token measured on this corpus; the chunkers work in
# characters so they stay dependency-free and fast to test.
CHARS_PER_TOKEN = 4.6

# Below the model's limit, leaving room for the tokenizer being less
# generous on a given passage than the corpus average suggests.
DEFAULT_CHUNK_TOKENS = 330


def build(conn, max_chars: int, min_chars: int, limit: int | None) -> int:
    pending = documents_needing_chunks(conn, min_chars=min_chars, limit=limit)
    print(f"model={model_name()} chunk<={max_chars} chars | {len(pending)} documents to chunk", flush=True)

    done = 0
    chunk_total = 0
    started = time.time()
    for document_id, text, document_type in pending:
        written = chunk_and_store(conn, document_id, text, document_type, max_chars=max_chars)
        if not written:
            continue

        done += 1
        chunk_total += written
        if done % 25 == 0 or done == len(pending):
            rate = done / max(time.time() - started, 1e-6)
            eta = (len(pending) - done) / rate / 60 if rate else float("inf")
            print(
                f"  {done}/{len(pending)} docs  {chunk_total} chunks  "
                f"{rate:.1f} docs/s  eta {eta:.0f} min",
                flush=True,
            )

    return chunk_total


def main() -> None:
    parser = argparse.ArgumentParser(description="Chunk and embed over-long documents.")
    parser.add_argument("--chunk-tokens", type=int, default=DEFAULT_CHUNK_TOKENS)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--limit", type=int, default=None, help="Chunk at most N documents.")
    args = parser.parse_args()

    max_chars = int(args.chunk_tokens * CHARS_PER_TOKEN)

    conn = get_connection()
    try:
        ensure_chunk_schema(conn)
        chunk_total = build(conn, max_chars, max_chars, args.limit)

        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM document_chunks")
            stored = cur.fetchone()[0]
            cur.execute(
                "SELECT count(*) FROM documents d WHERE d.document_type = ANY(%s) "
                "AND length(d.full_text) > %s AND NOT EXISTS "
                "(SELECT 1 FROM document_chunks c WHERE c.document_id = d.document_id)",
                (["section", "judgment"], max_chars),
            )
            remaining = cur.fetchone()[0]

        print(f"\nwrote {chunk_total} chunks this run; {stored} chunks stored, {remaining} documents left")
        if remaining:
            print("re-run to continue (resumable)")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
