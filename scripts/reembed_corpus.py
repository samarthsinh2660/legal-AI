"""Re-embed the whole corpus with the currently-selected embedding model.

Required whenever EMBEDDING_MODEL changes: stored vectors and the column's
declared dimension must agree, and vectors from different models are not
comparable even at equal dimension.

Resumable by construction -- it asks the database what is still
un-embedded rather than tracking progress separately, so an interrupted
run is resumed by running it again, losing only the batch in flight.

    .venv/bin/python -m scripts.reembed_corpus --prepare   # once: clears + widens column
    .venv/bin/python -m scripts.reembed_corpus             # fill; safe to re-run

--prepare is destructive and therefore a separate explicit step, so the
fill phase can be re-run freely.
"""

from __future__ import annotations

import argparse
import time

from legal_ai.knowledge.static.chunk_store import CHUNKABLE_TYPES, DEFAULT_MAX_CHARS
from legal_ai.knowledge.static.db import get_connection
from legal_ai.knowledge.static.embeddings import embed_many, embedding_dim, model_name


def prepare(conn) -> None:
    """Clear existing vectors and widen the column to the new dimension.

    Unavoidably destructive: Postgres cannot change a vector column's
    dimension while rows hold vectors of the old one. full_text is
    untouched, so everything cleared here is recomputable.
    """
    dim = embedding_dim()
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM documents WHERE embedding IS NOT NULL")
        had = cur.fetchone()[0]
        # Chunks are embedded with the old model too, and vectors from
        # different models are not comparable. Dropping them here keeps a
        # half-migrated corpus from mixing the two; build_chunks rebuilds.
        cur.execute("SELECT count(*) FROM document_chunks")
        had_chunks = cur.fetchone()[0]
        cur.execute("DELETE FROM document_chunks")
        cur.execute("DROP INDEX IF EXISTS documents_embedding_hnsw")
        cur.execute("UPDATE documents SET embedding = NULL")
        cur.execute(f"ALTER TABLE documents ALTER COLUMN embedding TYPE vector({dim})")
        cur.execute(f"ALTER TABLE document_chunks ALTER COLUMN embedding TYPE vector({dim})")
    conn.commit()
    print(
        f"prepared: cleared {had} document vectors and {had_chunks} chunks, "
        f"columns are now vector({dim})",
        flush=True,
    )


# Documents that build_chunks will represent by chunks instead. Embedding
# them whole here would both waste time and hand them a truncated vector
# that build_chunks then discards.
_SKIP = "NOT (document_type = ANY(%s) AND length(full_text) > %s)"
_SKIP_PARAMS = [list(CHUNKABLE_TYPES), DEFAULT_MAX_CHARS]


def fill(conn, batch_size: int, limit: int | None) -> int:
    with conn.cursor() as cur:
        cur.execute(f"SELECT count(*) FROM documents WHERE embedding IS NULL AND {_SKIP}", _SKIP_PARAMS)
        remaining = cur.fetchone()[0]
    print(f"model={model_name()} dim={embedding_dim()} remaining={remaining}", flush=True)

    done = 0
    started = time.time()
    while True:
        if limit is not None and done >= limit:
            break
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT document_id, full_text FROM documents "
                f"WHERE embedding IS NULL AND {_SKIP} ORDER BY document_id LIMIT %s",
                [*_SKIP_PARAMS, batch_size],
            )
            rows = cur.fetchall()
        if not rows:
            break

        vectors = embed_many([text for _doc_id, text in rows], batch_size=batch_size)
        with conn.cursor() as cur:
            for (document_id, _text), vector in zip(rows, vectors):
                cur.execute(
                    "UPDATE documents SET embedding = %s WHERE document_id = %s",
                    (vector, document_id),
                )
        conn.commit()

        done += len(rows)
        rate = done / max(time.time() - started, 1e-6)
        left = max(remaining - done, 0)
        eta_min = (left / rate / 60) if rate > 0 else float("inf")
        print(f"  {done}/{remaining}  {rate:.1f} docs/s  eta {eta_min:.0f} min", flush=True)

    return done


def build_index(conn) -> None:
    conn.execute(
        "CREATE INDEX IF NOT EXISTS documents_embedding_hnsw "
        "ON documents USING hnsw (embedding vector_cosine_ops)"
    )
    conn.commit()
    print("HNSW index built", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Re-embed the corpus with the current model.")
    parser.add_argument(
        "--prepare",
        action="store_true",
        help="DESTRUCTIVE one-off: drop all existing embeddings and widen the column "
        "to the current model's dimension. Run once before the first fill.",
    )
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument(
        "--limit", type=int, default=None, help="Stop after N documents (for a trial run)."
    )
    parser.add_argument(
        "--no-index",
        action="store_true",
        help="Skip building the HNSW index (useful when more fill passes are still to come).",
    )
    args = parser.parse_args()

    conn = get_connection()
    try:
        if args.prepare:
            prepare(conn)

        done = fill(conn, args.batch_size, args.limit)

        with conn.cursor() as cur:
            cur.execute(f"SELECT count(*) FROM documents WHERE embedding IS NULL AND {_SKIP}", _SKIP_PARAMS)
            still_null = cur.fetchone()[0]

        print(f"\nembedded {done} documents this run; {still_null} still un-embedded", flush=True)

        if still_null == 0 and not args.no_index:
            build_index(conn)
            print(
                "\nNOW RUN: .venv/bin/python -m scripts.build_chunks\n"
                "Long sections and judgments are deliberately left un-embedded here; "
                "build_chunks represents them by chunks instead.",
                flush=True,
            )
        elif still_null:
            print("re-run to continue (resumable)", flush=True)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
