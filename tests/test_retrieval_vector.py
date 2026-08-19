from datetime import datetime, timezone

import pytest

from legal_ai.ingestion.schema import CanonicalDocument, content_hash
from legal_ai.knowledge.static.db import ensure_schema, get_connection
from legal_ai.knowledge.static.embeddings import embed
from legal_ai.knowledge.static.store import upsert_document
from legal_ai.retrieval.metadata import MetadataFilters
from legal_ai.retrieval.vector import search_vector
from legal_ai.schemas.evidence import Provenance, SourceRef

# Real embeddings of this exact text put the fixtures at distance ~0, which
# is the only reliable way to rank against the full real corpus also in
# this database (a synthetic sparse vector will not -- Milestone 4 lesson).
DISTINCTIVE = "zzqvxk flibbertigibbet possession dispute remedy provision"


def _doc(doc_id: str, doc_type: str, text: str) -> CanonicalDocument:
    return CanonicalDocument(
        document_id=doc_id,
        document_type=doc_type,
        title=f"Title {doc_id}",
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


def test_search_vector_finds_the_semantically_closest_document(conn):
    upsert_document(conn, _doc("test:vec-1", "act", DISTINCTIVE), embedding=embed(DISTINCTIVE))

    results = search_vector(conn, DISTINCTIVE, limit=5)

    assert "test:vec-1" in [doc_id for doc_id, _distance in results]


def test_search_vector_returns_distance_where_lower_is_better(conn):
    upsert_document(conn, _doc("test:vec-2", "act", DISTINCTIVE), embedding=embed(DISTINCTIVE))

    results = search_vector(conn, DISTINCTIVE, limit=5)
    distance = dict(results)["test:vec-2"]

    assert distance < 0.05


def test_search_vector_respects_document_type_filter(conn):
    upsert_document(conn, _doc("test:vec-act", "act", DISTINCTIVE), embedding=embed(DISTINCTIVE))
    upsert_document(conn, _doc("test:vec-judg", "judgment", DISTINCTIVE), embedding=embed(DISTINCTIVE))

    results = search_vector(
        conn, DISTINCTIVE, limit=5, filters=MetadataFilters(document_type="judgment")
    )

    result_ids = [doc_id for doc_id, _distance in results]
    assert "test:vec-judg" in result_ids
    assert "test:vec-act" not in result_ids


def test_search_vector_respects_limit(conn):
    results = search_vector(conn, DISTINCTIVE, limit=3)
    assert len(results) <= 3


def test_search_vector_excludes_results_beyond_the_relevance_floor(conn):
    # Nearest-neighbour search always returns *something*; the floor is what
    # stops a meaningless query from grounding an answer in irrelevant law.
    results = search_vector(conn, "quhwjxbz vurpleknack nonexistentterm", limit=5)

    assert results == []


def test_search_vector_without_a_floor_returns_raw_nearest_neighbours(conn):
    results = search_vector(
        conn, "quhwjxbz vurpleknack nonexistentterm", limit=5, max_distance=None
    )

    assert len(results) == 5
    assert all(distance > 0.65 for _doc_id, distance in results)


def test_search_vector_still_finds_a_genuinely_relevant_real_query(conn):
    # Guards the floor against being set so tight it suppresses real hits.
    results = search_vector(conn, "punishment for criminal breach of trust", limit=5)

    assert results != []
