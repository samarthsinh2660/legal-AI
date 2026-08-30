from datetime import datetime, timezone

import pytest

from legal_ai.ingestion.schema import CanonicalDocument, content_hash
from legal_ai.knowledge.static.db import ensure_retrieval_schema, ensure_schema, get_connection
from legal_ai.knowledge.static.store import upsert_document
from legal_ai.retrieval.keyword import search_keyword
from legal_ai.retrieval.metadata import MetadataFilters
from legal_ai.schemas.evidence import Provenance, SourceRef

# Nonsense term, so these fixtures are the only matches in a database that
# also holds the full real corpus.
DISTINCTIVE = "zzqvxk flibbertigibbet"


def _doc(doc_id: str, doc_type: str, title: str, text: str) -> CanonicalDocument:
    return CanonicalDocument(
        document_id=doc_id,
        document_type=doc_type,
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
    ensure_retrieval_schema(connection)
    yield connection
    with connection.cursor() as cur:
        cur.execute("DELETE FROM documents WHERE document_id LIKE 'test:%'")
    connection.commit()
    connection.close()


def test_search_keyword_finds_a_document_by_its_body_text(conn):
    upsert_document(conn, _doc("test:kw-1", "act", "Ordinary Title", f"{DISTINCTIVE} provision here"))

    results = search_keyword(conn, DISTINCTIVE)

    assert [doc_id for doc_id, _score in results] == ["test:kw-1"]
    assert results[0][1] > 0


def test_search_keyword_returns_empty_for_no_match(conn):
    assert search_keyword(conn, "quhwjxbz nonexistentterm") == []


def test_search_keyword_respects_document_type_filter(conn):
    upsert_document(conn, _doc("test:kw-act", "act", "Ordinary Title", f"{DISTINCTIVE} provision"))
    upsert_document(conn, _doc("test:kw-judg", "judgment", "Ordinary Title", f"{DISTINCTIVE} provision"))

    results = search_keyword(conn, DISTINCTIVE, filters=MetadataFilters(document_type="judgment"))

    assert [doc_id for doc_id, _score in results] == ["test:kw-judg"]


def test_search_keyword_respects_limit(conn):
    for index in range(3):
        upsert_document(conn, _doc(f"test:kw-lim-{index}", "act", "Ordinary Title", f"{DISTINCTIVE} text"))

    results = search_keyword(conn, DISTINCTIVE, limit=2)

    assert len(results) == 2


def test_search_keyword_handles_a_multi_word_natural_language_query(conn):
    upsert_document(
        conn, _doc("test:kw-nl", "act", "Ordinary Title", f"{DISTINCTIVE} possession and compensation")
    )

    results = search_keyword(conn, f"{DISTINCTIVE} compensation")

    assert "test:kw-nl" in [doc_id for doc_id, _score in results]
