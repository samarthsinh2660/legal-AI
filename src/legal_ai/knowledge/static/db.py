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
