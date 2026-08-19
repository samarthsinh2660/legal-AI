from datetime import datetime, timezone

import pytest

from legal_ai.ingestion.schema import CanonicalDocument, content_hash
from legal_ai.knowledge.static.db import ensure_retrieval_schema, ensure_schema, get_connection
from legal_ai.knowledge.static.store import upsert_document
from legal_ai.schemas.evidence import Provenance, SourceRef


def _doc(doc_id: str, title: str, text: str) -> CanonicalDocument:
    return CanonicalDocument(
        document_id=doc_id,
        document_type="act",
        title=title,
        full_text=text,
        content_hash=content_hash(text),
        provenance=Provenance(
            source=SourceRef(name="India Code", url="https://x", source_type="primary"),
            retrieved_at=datetime(2026, 8, 19, tzinfo=timezone.utc),
            licence="Government of India",
            attribution_required=False,
        ),
        ingested_at=datetime(2026, 8, 19, tzinfo=timezone.utc),
    )


@pytest.fixture
def conn():
    connection = get_connection()
    ensure_schema(connection)
    yield connection
    with connection.cursor() as cur:
        cur.execute("DELETE FROM documents WHERE document_id LIKE 'test:%'")
    connection.commit()
    connection.close()


def test_ensure_retrieval_schema_creates_column_and_indexes(conn):
    result = ensure_retrieval_schema(conn)

    assert result["search_vector_column"] is True
    assert result["keyword_index"] is True

    with conn.cursor() as cur:
        cur.execute("SELECT indexname FROM pg_indexes WHERE tablename = 'documents'")
        index_names = {row[0] for row in cur.fetchall()}
    assert "documents_search_vector_gin" in index_names


def test_ensure_retrieval_schema_is_idempotent(conn):
    ensure_retrieval_schema(conn)
    second = ensure_retrieval_schema(conn)

    assert second["search_vector_column"] is True
    assert second["keyword_index"] is True


def test_search_vector_column_is_populated_for_new_rows(conn):
    ensure_retrieval_schema(conn)
    upsert_document(conn, _doc("test:fts-1", "Ordinary Title", "zzqvxk flibbertigibbet provision"))

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT search_vector @@ websearch_to_tsquery('english', 'flibbertigibbet')
            FROM documents WHERE document_id = 'test:fts-1'
            """
        )
        matched = cur.fetchone()[0]
    assert matched is True


def test_search_vector_column_indexes_the_title_too(conn):
    ensure_retrieval_schema(conn)
    upsert_document(conn, _doc("test:fts-2", "Zzqvxk Distinctive Heading", "ordinary body text"))

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT search_vector @@ websearch_to_tsquery('english', 'Zzqvxk')
            FROM documents WHERE document_id = 'test:fts-2'
            """
        )
        matched = cur.fetchone()[0]
    assert matched is True
