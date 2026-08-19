"""Postgres connection for the canonical static store.

Connects to the docker-compose Postgres (pgvector/pgvector:pg16) started
per docs/superpowers/specs/2026-08-15-phase1-ingestion-design.md §3.5.
"""

from __future__ import annotations

import os

import psycopg
from pgvector.psycopg import register_vector

# Embedding dimension for the Task 1 default model, all-MiniLM-L6-v2.
EMBEDDING_DIM = 384

_DEFAULT_DSN = "postgresql://legal_ai:legal_ai_dev@localhost:5433/legal_ai"


def get_connection() -> psycopg.Connection:
    dsn = os.environ.get("DATABASE_URL", _DEFAULT_DSN)
    conn = psycopg.connect(dsn, autocommit=False)
    conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
    conn.commit()
    register_vector(conn)
    return conn


def ensure_retrieval_schema(conn: psycopg.Connection) -> dict[str, bool]:
    """Additive, idempotent indexes for hybrid retrieval (Phase 2 Milestone 5).

    Separate from ensure_schema() because these are retrieval concerns, not
    the canonical document contract -- Phase 1 ingestion works without them.

    Returns which structures are in place. "vector_index" can legitimately
    come back False: an HNSW index needs a fixed-dimension vector column,
    and if the corpus ever holds mixed embedding dimensions the index is
    skipped rather than raising, degrading to the sequential scan that was
    the behaviour before this function existed.
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

        # pgvector encodes a vector column's declared dimension in atttypmod;
        # a bare VECTOR (no dimension) is -1, and HNSW cannot index that.
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
            if dims not in ([EMBEDDING_DIM], []):
                return False
            cur.execute(
                f"ALTER TABLE documents ALTER COLUMN embedding TYPE vector({EMBEDDING_DIM})"
            )

    conn.commit()
    conn.execute(
        "CREATE INDEX IF NOT EXISTS documents_embedding_hnsw "
        "ON documents USING hnsw (embedding vector_cosine_ops)"
    )
    conn.commit()
    return True


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
