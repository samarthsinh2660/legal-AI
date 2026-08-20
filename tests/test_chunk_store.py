from datetime import datetime, timezone

import pytest

from legal_ai.ingestion.schema import CanonicalDocument, content_hash
from legal_ai.knowledge.static.chunk_store import (
    delete_chunks,
    documents_needing_chunks,
    get_chunks,
    upsert_chunks,
)
from legal_ai.knowledge.static.db import ensure_chunk_schema, ensure_schema, get_connection
from legal_ai.knowledge.static.embeddings import embed, embedding_dim
from legal_ai.knowledge.static.store import upsert_document
from legal_ai.retrieval.chunking import Chunk
from legal_ai.schemas.evidence import Provenance, SourceRef

LONG = "(1) " + ("a long statutory provision about possession and refund " * 60)


def _doc(doc_id: str, doc_type: str, text: str) -> CanonicalDocument:
    return CanonicalDocument(
        document_id=doc_id,
        document_type=doc_type,
        title=f"Title {doc_id}",
        full_text=text,
        content_hash=content_hash(text),
        provenance=Provenance(
            source=SourceRef(name="India Code", url="https://x", source_type="primary"),
            retrieved_at=datetime(2026, 8, 20, tzinfo=timezone.utc),
            licence="Government of India",
            attribution_required=False,
        ),
        ingested_at=datetime(2026, 8, 20, tzinfo=timezone.utc),
    )


@pytest.fixture
def conn():
    connection = get_connection()
    ensure_schema(connection)
    ensure_chunk_schema(connection)
    yield connection
    with connection.cursor() as cur:
        cur.execute("DELETE FROM document_chunks WHERE document_id LIKE 'test:%'")
        cur.execute("DELETE FROM documents WHERE document_id LIKE 'test:%'")
    connection.commit()
    connection.close()


def test_upsert_and_get_chunks_round_trip(conn):
    upsert_document(conn, _doc("test:c-1", "section", LONG))
    chunks = [Chunk(text="first piece", ordinal=0, label="(1)"),
              Chunk(text="second piece", ordinal=1, label="(2)")]

    upsert_chunks(conn, "test:c-1", chunks, [embed(c.text) for c in chunks])
    stored = get_chunks(conn, "test:c-1")

    assert [c.ordinal for c in stored] == [0, 1]
    assert [c.label for c in stored] == ["(1)", "(2)"]
    assert stored[0].text == "first piece"


def test_upsert_chunks_replaces_previous_chunks_for_that_document(conn):
    upsert_document(conn, _doc("test:c-2", "section", LONG))
    first = [Chunk(text="old a", ordinal=0), Chunk(text="old b", ordinal=1)]
    upsert_chunks(conn, "test:c-2", first, [embed(c.text) for c in first])

    second = [Chunk(text="new only", ordinal=0)]
    upsert_chunks(conn, "test:c-2", second, [embed(c.text) for c in second])

    stored = get_chunks(conn, "test:c-2")
    assert len(stored) == 1
    assert stored[0].text == "new only"


def test_chunk_embeddings_have_the_model_dimension(conn):
    upsert_document(conn, _doc("test:c-3", "section", LONG))
    chunks = [Chunk(text="a piece of statute", ordinal=0)]
    upsert_chunks(conn, "test:c-3", chunks, [embed(chunks[0].text)])

    with conn.cursor() as cur:
        cur.execute(
            "SELECT vector_dims(embedding) FROM document_chunks WHERE document_id = 'test:c-3'"
        )
        assert cur.fetchone()[0] == embedding_dim()


def test_documents_needing_chunks_finds_only_long_unchunked_documents(conn):
    upsert_document(conn, _doc("test:c-long", "section", LONG), embedding=embed(LONG))
    upsert_document(conn, _doc("test:c-short", "section", "tiny"), embedding=embed("tiny"))

    pending = documents_needing_chunks(conn, min_chars=500)
    ids = [doc_id for doc_id, _text, _type in pending]

    assert "test:c-long" in ids
    assert "test:c-short" not in ids


def test_documents_needing_chunks_excludes_acts(conn):
    # An Act's text is its sections concatenated, and those are embedded
    # individually; chunking Acts would duplicate them.
    upsert_document(conn, _doc("test:c-act", "act", LONG), embedding=embed(LONG))

    ids = [doc_id for doc_id, _t, _ty in documents_needing_chunks(conn, min_chars=500)]
    assert "test:c-act" not in ids


def test_documents_needing_chunks_skips_already_chunked_documents(conn):
    upsert_document(conn, _doc("test:c-done", "section", LONG), embedding=embed(LONG))
    chunks = [Chunk(text="already done", ordinal=0)]
    upsert_chunks(conn, "test:c-done", chunks, [embed(chunks[0].text)])

    ids = [doc_id for doc_id, _t, _ty in documents_needing_chunks(conn, min_chars=500)]
    assert "test:c-done" not in ids


def test_delete_chunks_removes_them(conn):
    upsert_document(conn, _doc("test:c-del", "section", LONG))
    chunks = [Chunk(text="doomed", ordinal=0)]
    upsert_chunks(conn, "test:c-del", chunks, [embed(chunks[0].text)])

    delete_chunks(conn, "test:c-del")

    assert get_chunks(conn, "test:c-del") == []


def test_deleting_the_parent_document_removes_its_chunks(conn):
    upsert_document(conn, _doc("test:c-cascade", "section", LONG))
    chunks = [Chunk(text="child chunk", ordinal=0)]
    upsert_chunks(conn, "test:c-cascade", chunks, [embed(chunks[0].text)])

    with conn.cursor() as cur:
        cur.execute("DELETE FROM documents WHERE document_id = 'test:c-cascade'")
    conn.commit()

    assert get_chunks(conn, "test:c-cascade") == []


def test_chunk_and_store_chunks_a_long_document_and_clears_its_embedding(conn):
    from legal_ai.knowledge.static.chunk_store import chunk_and_store

    upsert_document(conn, _doc("test:cas-long", "section", LONG), embedding=embed(LONG))

    count = chunk_and_store(conn, "test:cas-long", LONG, "section", max_chars=600)

    assert count > 1
    assert len(get_chunks(conn, "test:cas-long")) == count
    with conn.cursor() as cur:
        cur.execute("SELECT embedding IS NULL FROM documents WHERE document_id = 'test:cas-long'")
        assert cur.fetchone()[0] is True


def test_chunk_and_store_leaves_a_short_document_alone(conn):
    from legal_ai.knowledge.static.chunk_store import chunk_and_store

    short = "A short provision."
    upsert_document(conn, _doc("test:cas-short", "section", short), embedding=embed(short))

    count = chunk_and_store(conn, "test:cas-short", short, "section", max_chars=600)

    assert count == 0
    assert get_chunks(conn, "test:cas-short") == []
    with conn.cursor() as cur:
        cur.execute("SELECT embedding IS NULL FROM documents WHERE document_id = 'test:cas-short'")
        assert cur.fetchone()[0] is False


def test_chunk_and_store_uses_the_judgment_splitter_for_judgments(conn):
    from legal_ai.knowledge.static.chunk_store import chunk_and_store

    text = "".join(f"{n}. Paragraph {n} of this judgment discusses the matter at hand.\n" for n in range(1, 12))
    upsert_document(conn, _doc("test:cas-judg", "judgment", text), embedding=embed(text))

    chunk_and_store(conn, "test:cas-judg", text, "judgment", max_chars=200)

    labels = [c.label for c in get_chunks(conn, "test:cas-judg")]
    assert any(label and label.isdigit() for label in labels)
