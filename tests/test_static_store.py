from datetime import datetime, timezone

import pytest

from legal_ai.ingestion.schema import CanonicalDocument, content_hash
from legal_ai.knowledge.static.db import EMBEDDING_DIM, ensure_schema, get_connection
from legal_ai.knowledge.static.store import find_similar, get_document, upsert_document
from legal_ai.schemas.evidence import Provenance, SourceRef


def _sparse_vector(*hot_positions_and_values: tuple[int, float]) -> list[float]:
    """A near-orthogonal EMBEDDING_DIM-length vector, real value only at
    the given positions. Real ingested rows are always EMBEDDING_DIM-long
    (pgvector's <=> operator errors on a dimension mismatch), so a fixture
    vector shorter than that would break find_similar as soon as any real
    document exists in the same table — see Task 12's live ingestion."""
    vector = [0.0] * EMBEDDING_DIM
    for position, value in hot_positions_and_values:
        vector[position] = value
    return vector


def _doc(doc_id: str, text: str) -> CanonicalDocument:
    return CanonicalDocument(
        document_id=doc_id,
        document_type="act",
        title=f"Title for {doc_id}",
        full_text=text,
        content_hash=content_hash(text),
        provenance=Provenance(
            source=SourceRef(name="India Code", url="https://x", source_type="primary"),
            retrieved_at=datetime(2026, 8, 15, tzinfo=timezone.utc),
            licence="Government of India",
            attribution_required=False,
        ),
        ingested_at=datetime(2026, 8, 15, tzinfo=timezone.utc),
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


def test_upsert_inserts_new_document_and_get_returns_it(conn):
    doc = _doc("test:1", "Some legal text")
    changed = upsert_document(conn, doc)
    assert changed is True

    restored = get_document(conn, "test:1")
    assert restored is not None
    assert restored.title == "Title for test:1"
    assert restored.content_hash == doc.content_hash


def test_upsert_is_idempotent_for_unchanged_content(conn):
    doc = _doc("test:2", "Unchanged text")
    assert upsert_document(conn, doc) is True
    assert upsert_document(conn, doc) is False  # same content_hash, no-op


def test_upsert_updates_when_content_changes(conn):
    doc_v1 = _doc("test:3", "Version one")
    upsert_document(conn, doc_v1)
    doc_v2 = _doc("test:3", "Version two")
    changed = upsert_document(conn, doc_v2)
    assert changed is True
    restored = get_document(conn, "test:3")
    assert restored.full_text == "Version two"


def test_get_document_returns_none_for_missing_id(conn):
    assert get_document(conn, "test:does-not-exist") is None


def test_find_similar_returns_nearest_by_embedding(conn):
    upsert_document(conn, _doc("test:4", "about adverse possession"), embedding=_sparse_vector((0, 1.0)))
    upsert_document(conn, _doc("test:5", "about contract law"), embedding=_sparse_vector((1, 1.0)))

    results = find_similar(conn, query_embedding=_sparse_vector((0, 0.9), (1, 0.1)), limit=1)

    assert len(results) == 1
    assert results[0][0].document_id == "test:4"
