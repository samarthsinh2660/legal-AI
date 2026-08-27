from datetime import datetime, timezone

import pytest

from legal_ai.ingestion.schema import CanonicalDocument, content_hash
from legal_ai.knowledge.static.db import ensure_schema, get_connection
from legal_ai.knowledge.static.embeddings import embed
from legal_ai.knowledge.static.store import upsert_document
from legal_ai.retrieval.metadata import MetadataFilters
from legal_ai.retrieval.vector import DEFAULT_MAX_DISTANCE, search_vector
from legal_ai.schemas.evidence import Provenance, SourceRef

# Seeded with a real embedding of this exact text so the fixtures sit at
# distance ~0 and rank above the full real corpus in this database. A
# synthetic sparse vector would not rank.
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


def test_search_vector_applies_an_explicitly_given_floor(conn):
    # No floor is applied by default -- distances of correct answers and of
    # nonsense overlap on this corpus, so no cut-off separates them. A
    # caller may still impose one.
    results = search_vector(conn, "possession of immovable property", limit=20, max_distance=0.4)

    assert all(distance <= 0.4 for _doc_id, distance in results)


def test_search_vector_has_no_floor_by_default(conn):
    assert DEFAULT_MAX_DISTANCE is None
    assert search_vector(conn, "zxcvbnm qwertyuiop asdfghjkl", limit=5) != []


def test_search_vector_without_a_floor_returns_raw_nearest_neighbours(conn):
    results = search_vector(
        conn, "zxcvbnm qwertyuiop asdfghjkl", limit=5, max_distance=None
    )

    assert len(results) == 5
    assert all(distance > 0.5 for _doc_id, distance in results)


def test_search_vector_still_finds_a_genuinely_relevant_real_query(conn):
    # Guards the floor against being set so tight it suppresses real hits.
    results = search_vector(conn, "punishment for criminal breach of trust", limit=5)

    assert results != []


def test_search_vector_finds_a_document_through_its_chunks(conn):
    # A long document whose own embedding is NULL (because it was chunked)
    # must still be findable via the chunk that actually matches.
    from legal_ai.knowledge.static.chunk_store import upsert_chunks
    from legal_ai.knowledge.static.db import ensure_chunk_schema
    from legal_ai.retrieval.chunking import Chunk

    ensure_chunk_schema(conn)
    body = "irrelevant preamble text " * 40 + DISTINCTIVE
    doc = _doc("test:vec-chunked", "section", body)
    upsert_document(conn, doc, embedding=None)
    chunk = Chunk(text=DISTINCTIVE, ordinal=0, label="(1)")
    upsert_chunks(conn, "test:vec-chunked", [chunk], [embed(DISTINCTIVE)])

    results = search_vector(conn, DISTINCTIVE, limit=5)

    assert "test:vec-chunked" in [doc_id for doc_id, _d in results]


def test_search_vector_reports_each_document_once_not_once_per_chunk(conn):
    from legal_ai.knowledge.static.chunk_store import upsert_chunks
    from legal_ai.knowledge.static.db import ensure_chunk_schema
    from legal_ai.retrieval.chunking import Chunk

    ensure_chunk_schema(conn)
    doc = _doc("test:vec-multi", "section", DISTINCTIVE * 5)
    upsert_document(conn, doc, embedding=None)
    chunks = [Chunk(text=DISTINCTIVE, ordinal=i) for i in range(3)]
    upsert_chunks(conn, "test:vec-multi", chunks, [embed(c.text) for c in chunks])

    results = search_vector(conn, DISTINCTIVE, limit=10)
    ids = [doc_id for doc_id, _d in results]

    assert ids.count("test:vec-multi") == 1


# --- HNSW recall: added 2026-08-27 -------------------------------------

def test_an_out_of_distribution_query_still_returns_nearest_neighbours(conn):
    """Empty must mean "nothing stored", never "the index gave up".

    HNSW's default ef_search of 40 returned 0 rows for this query against
    107k vectors while nearest neighbours sat at distance 0.72, reachable
    by exact scan. A query the corpus cannot answer well and a query the
    corpus cannot answer at all must not look identical.
    """
    results = search_vector(conn, "zxcvbnm qwertyuiop asdfghjkl", limit=5)

    assert len(results) == 5
    # Genuinely far away -- this is recall, not a claim of relevance.
    assert all(distance > 0.5 for _doc_id, distance in results)


def test_ef_search_is_set_high_enough_for_the_limit_asked_for():
    # ef_search below the requested limit cannot return that many rows.
    from legal_ai.retrieval.vector import HNSW_EF_SEARCH

    from legal_ai.config import DEFAULT_CONFIG

    assert HNSW_EF_SEARCH >= DEFAULT_CONFIG.search_limit
