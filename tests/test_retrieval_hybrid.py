from datetime import datetime, timezone

import pytest

from legal_ai.ingestion.schema import CanonicalDocument, content_hash
from legal_ai.knowledge.static.db import ensure_retrieval_schema, ensure_schema, get_connection
from legal_ai.knowledge.static.embeddings import embed
from legal_ai.knowledge.static.store import upsert_document
from legal_ai.retrieval.hybrid import hybrid_search, reciprocal_rank_fusion
from legal_ai.retrieval.metadata import MetadataFilters
from legal_ai.schemas.evidence import Provenance, SourceRef

DISTINCTIVE = "zzqvxk flibbertigibbet possession dispute remedy provision"


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


def test_fusion_ranks_a_document_found_by_two_signals_above_one_found_by_one():
    keyword_results = [("doc-a", 0.9), ("doc-b", 0.5)]
    vector_results = [("doc-a", 0.01)]

    fused = reciprocal_rank_fusion([keyword_results, vector_results])

    assert [doc_id for doc_id, _score in fused][0] == "doc-a"
    assert dict(fused)["doc-a"] > dict(fused)["doc-b"]


def test_fusion_uses_rank_not_raw_score():
    # doc-b's raw score is far larger but it ranks second in its own list;
    # a document ranked first elsewhere must not lose on scale alone.
    list_one = [("doc-a", 0.001)]
    list_two = [("doc-c", 999.0), ("doc-b", 998.0)]

    fused = dict(reciprocal_rank_fusion([list_one, list_two]))

    assert fused["doc-a"] == fused["doc-c"]
    assert fused["doc-a"] > fused["doc-b"]


def test_fusion_of_no_lists_is_empty():
    assert reciprocal_rank_fusion([]) == []


def test_fusion_ignores_empty_signal_lists():
    fused = reciprocal_rank_fusion([[], [("doc-a", 1.0)], []])
    assert [doc_id for doc_id, _score in fused] == ["doc-a"]


def test_hybrid_search_finds_a_document_matching_on_both_keyword_and_vector(conn):
    upsert_document(
        conn, _doc("test:h-1", "act", "Ordinary Title", DISTINCTIVE), embedding=embed(DISTINCTIVE)
    )

    results = hybrid_search(DISTINCTIVE, limit=5, expand_graph=False)

    assert "test:h-1" in [e.document_id for e in results]


def test_hybrid_search_returns_evidence_objects(conn):
    upsert_document(
        conn, _doc("test:h-2", "act", "Ordinary Title", DISTINCTIVE), embedding=embed(DISTINCTIVE)
    )

    results = hybrid_search(DISTINCTIVE, limit=5, expand_graph=False)
    match = next(e for e in results if e.document_id == "test:h-2")

    assert match.content == DISTINCTIVE
    assert match.document_type == "act"
    assert match.provenance.source.name == "India Code"


def test_hybrid_search_respects_the_limit(conn):
    results = hybrid_search(DISTINCTIVE, limit=3, expand_graph=False)
    assert len(results) <= 3


def test_hybrid_search_respects_metadata_filters(conn):
    upsert_document(
        conn, _doc("test:h-act", "act", "Ordinary Title", DISTINCTIVE), embedding=embed(DISTINCTIVE)
    )
    upsert_document(
        conn, _doc("test:h-judg", "judgment", "Ordinary Title", DISTINCTIVE), embedding=embed(DISTINCTIVE)
    )

    results = hybrid_search(
        DISTINCTIVE, limit=10, filters=MetadataFilters(document_type="judgment"), expand_graph=False
    )

    result_ids = [e.document_id for e in results]
    assert "test:h-judg" in result_ids
    assert "test:h-act" not in result_ids


def test_hybrid_search_returns_empty_when_nothing_matches(conn):
    results = hybrid_search("quhwjxbz vurpleknack nonexistentterm", limit=5, expand_graph=False)
    assert results == []


def test_hybrid_search_with_reranking_returns_evidence(conn):
    upsert_document(
        conn, _doc("test:h-rr", "act", "Ordinary Title", DISTINCTIVE), embedding=embed(DISTINCTIVE)
    )

    results = hybrid_search(DISTINCTIVE, limit=5, expand_graph=False, rerank=True)

    assert results
    assert all(e.document_id and e.content for e in results)
    assert len(results) <= 5


def test_reranking_widens_the_candidate_pool_it_is_given(conn):
    # The reranker's value comes from rescuing documents at deep ranks, so
    # the signals must fetch at least the shortlist size, not limit*3.
    from legal_ai.retrieval.hybrid import RERANK_CANDIDATES

    captured = {}
    import legal_ai.retrieval.hybrid as hybrid_module

    original = hybrid_module.search_vector

    def spy(conn_, query_, limit=10, filters=None, **kwargs):
        captured["limit"] = limit
        return original(conn_, query_, limit=limit, filters=filters, **kwargs)

    hybrid_module.search_vector = spy
    try:
        hybrid_search(DISTINCTIVE, limit=5, expand_graph=False, rerank=True)
    finally:
        hybrid_module.search_vector = original

    assert captured["limit"] >= RERANK_CANDIDATES
