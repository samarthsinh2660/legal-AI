"""Postgres connection for the canonical static store.

Connects to the docker-compose Postgres (pgvector/pgvector:pg16) started
per docs/superpowers/specs/2026-08-15-phase1-ingestion-design.md §3.5.
"""

from __future__ import annotations

import os

import psycopg
from pgvector.psycopg import register_vector

from legal_ai.knowledge.static.embeddings import embedding_dim


def _embedding_dim() -> int:
    """Dimension of the currently-selected embedding model.

    Read through a function, not frozen at import, so overriding
    EMBEDDING_MODEL cannot leave schema and vectors disagreeing.
    """
    return embedding_dim()


# Import-time snapshot kept for backwards compatibility. Prefer
# _embedding_dim() in new code; this will not follow a later
# EMBEDDING_MODEL change.
EMBEDDING_DIM = embedding_dim()

_DEFAULT_DSN = "postgresql://legal_ai:legal_ai_dev@localhost:5433/legal_ai"


def get_connection() -> psycopg.Connection:
    dsn = os.environ.get("DATABASE_URL", _DEFAULT_DSN)
    conn = psycopg.connect(dsn, autocommit=False)
    conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
    conn.commit()
    register_vector(conn)
    return conn


def ensure_retrieval_schema(conn: psycopg.Connection) -> dict[str, bool]:
    """Additive, idempotent indexes for hybrid retrieval.

    Separate from ensure_schema() because these are retrieval concerns;
    ingestion works without them.

    Returns which structures are in place. "vector_index" may be False:
    HNSW needs a fixed-dimension column, so a corpus with mixed embedding
    dimensions falls back to a sequential scan rather than raising.
    """
    conn.execute(
        """
        ALTER TABLE documents ADD COLUMN IF NOT EXISTS search_vector tsvector
        GENERATED ALWAYS AS (
            to_tsvector('english', coalesce(title, '') || ' ' || coalesce(full_text, ''))
        ) STORED
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS documents_search_vector_gin
        ON documents USING GIN (search_vector)
        """
    )
    conn.commit()

    ensure_chunk_schema(conn)
    vector_index = _ensure_vector_index(conn)
    return {
        "search_vector_column": True,
        "keyword_index": True,
        "vector_index": vector_index,
    }


def _ensure_vector_index(conn: psycopg.Connection) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT 1 FROM pg_indexes WHERE tablename = 'documents' "
            "AND indexname = 'documents_embedding_hnsw'"
        )
        if cur.fetchone() is not None:
            return True

        # pgvector stores a column's declared dimension in atttypmod; a
        # bare VECTOR is -1, which HNSW cannot index.
        cur.execute(
            "SELECT atttypmod FROM pg_attribute "
            "WHERE attrelid = 'documents'::regclass AND attname = 'embedding'"
        )
        typmod = cur.fetchone()[0]

        if typmod < 0:
            cur.execute(
                "SELECT DISTINCT vector_dims(embedding) FROM documents WHERE embedding IS NOT NULL"
            )
            dims = [row[0] for row in cur.fetchall()]
            if dims not in ([_embedding_dim()], []):
                return False
            cur.execute(
                f"ALTER TABLE documents ALTER COLUMN embedding TYPE vector({_embedding_dim()})"
            )

    conn.commit()
    conn.execute(
        "CREATE INDEX IF NOT EXISTS documents_embedding_hnsw "
        "ON documents USING hnsw (embedding vector_cosine_ops)"
    )
    conn.commit()
    return True


def ensure_chunk_schema(conn: psycopg.Connection) -> None:
    """Table holding embeddable pieces of documents too long to embed whole.

    Kept out of `documents`, which is the canonical store: chunks are a
    retrieval-layer artifact and must be re-buildable without touching
    canonical data. ON DELETE CASCADE keeps them from outliving a parent.
    """
    dim = _embedding_dim()
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS document_chunks (
            chunk_id TEXT PRIMARY KEY,
            document_id TEXT NOT NULL REFERENCES documents(document_id) ON DELETE CASCADE,
            ordinal INT NOT NULL,
            label TEXT,
            text TEXT NOT NULL,
            embedding vector({dim}),
            UNIQUE (document_id, ordinal)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS document_chunks_document_id_idx "
        "ON document_chunks (document_id)"
    )
    conn.commit()
    conn.execute(
        "CREATE INDEX IF NOT EXISTS document_chunks_embedding_hnsw "
        "ON document_chunks USING hnsw (embedding vector_cosine_ops)"
    )
    conn.commit()


def ensure_schema(conn: psycopg.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS documents (
            document_id TEXT PRIMARY KEY,
            document_type TEXT NOT NULL,
            title TEXT NOT NULL,
            court TEXT,
            citation TEXT,
            case_number TEXT,
            parties JSONB,
            decision_date DATE,
            enactment_date DATE,
            disposal_nature TEXT,
            act_id TEXT,
            full_text TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            provenance JSONB NOT NULL,
            ingested_at TIMESTAMPTZ NOT NULL,
            embedding VECTOR
        )
        """
    )
    conn.commit()
    ensure_version_schema(conn)
    ensure_bench_schema(conn)


def ensure_bench_schema(conn: psycopg.Connection) -> None:
    """Bench columns on `documents`, added rather than threaded through the
    canonical upsert.

    Bench is derived from the judgment's own text, not supplied by the
    archive, so it is not a field of CanonicalDocument and does not belong
    in the INSERT that statutes also travel through. Keeping it additive
    means the statute path is untouched.

    `bench_size` is NULL when the header could not be parsed. NULL means
    unknown and must not be read as small -- an unparsed Constitution Bench
    outranks everything, and defaulting it to 1 would silently invert the
    ordering this column exists to provide.

    The catalog is checked before any ALTER is issued. `ADD COLUMN IF NOT
    EXISTS` still requests ACCESS EXCLUSIVE even when it is a no-op, and a
    *pending* ACCESS EXCLUSIVE request blocks every reader that queues
    behind it. Measured 2026-08-29: called once per stored judgment during
    a bulk ingest, this took the whole database down for readers for over
    half an hour -- every search in every other process sat waiting on an
    ALTER that had nothing to do.
    """
    existing = conn.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = 'documents' AND column_name IN ('judges', 'bench_size') AND table_schema = current_schema()"
    ).fetchall()
    if len({row[0] for row in existing}) == 2:
        conn.commit()
        return

    conn.execute("ALTER TABLE documents ADD COLUMN IF NOT EXISTS judges JSONB")
    conn.execute("ALTER TABLE documents ADD COLUMN IF NOT EXISTS bench_size INT")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS documents_bench_size_idx "
        "ON documents (bench_size DESC NULLS LAST)"
    )
    conn.commit()


def ensure_version_schema(conn: psycopg.Connection) -> None:
    """History of superseded document text.

    `documents` always holds current law -- every retrieval path reads it
    unchanged and needs no date predicate. When re-ingestion finds the
    text of a stored document has changed, the *old* row is copied here
    before being overwritten, so an amendment never destroys the text it
    replaced.

    On the two timestamps, which are observation times and not legal
    dates: `first_seen_at` is when we ingested that text, `superseded_at`
    is when we ingested something different. Neither is the date
    Parliament commenced an amendment -- India Code does not give us one.
    A version therefore bounds when the text changed to within our polling
    interval, and that is all it claims. Callers that need a true
    commencement date must get it elsewhere.
    """
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS document_versions (
            version_id BIGSERIAL PRIMARY KEY,
            document_id TEXT NOT NULL,
            title TEXT NOT NULL,
            full_text TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            provenance JSONB NOT NULL,
            first_seen_at TIMESTAMPTZ NOT NULL,
            superseded_at TIMESTAMPTZ NOT NULL
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS document_versions_lookup_idx "
        "ON document_versions (document_id, superseded_at)"
    )
    conn.commit()
