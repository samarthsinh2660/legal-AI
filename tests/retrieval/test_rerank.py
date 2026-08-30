import pytest

from legal_ai.retrieval import rerank as rr


def test_known_rerankers_are_registered():
    assert "cross-encoder/ms-marco-MiniLM-L-12-v2" in rr.KNOWN_RERANKERS
    assert "cross-encoder/ms-marco-MiniLM-L-6-v2" in rr.KNOWN_RERANKERS


def test_reranker_name_defaults_to_the_configured_default():
    assert rr.reranker_name() == rr.DEFAULT_RERANKER


def test_reranker_can_be_switched_by_environment(monkeypatch):
    monkeypatch.setenv("RERANK_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2")
    assert rr.reranker_name() == "cross-encoder/ms-marco-MiniLM-L-6-v2"


def test_unregistered_reranker_is_rejected_rather_than_loaded(monkeypatch):
    # A silent typo would otherwise download an arbitrary model and rank
    # results with it.
    monkeypatch.setenv("RERANK_MODEL", "nobody/registered-this")
    with pytest.raises(KeyError):
        rr.reranker_name()


def test_rerank_of_nothing_is_empty():
    assert rr.rerank("any query", []) == []


def test_rerank_returns_the_same_documents_reordered():
    candidates = [
        ("doc-unrelated", "The tiger is a large cat native to Asia and hunts alone."),
        ("doc-relevant", "If the promoter fails to give possession the allottee may claim a refund."),
        ("doc-other", "Photosynthesis converts light energy into chemical energy in plants."),
    ]

    ranked = rr.rerank("builder did not hand over my flat, can I get my money back", candidates)

    assert {doc_id for doc_id, _score in ranked} == {c[0] for c in candidates}
    assert ranked[0][0] == "doc-relevant"


def test_rerank_respects_limit():
    candidates = [(f"doc-{i}", f"Some legal provision number {i} about contracts.") for i in range(6)]
    assert len(rr.rerank("contract provision", candidates, limit=2)) == 2


def test_rerank_scores_descend():
    candidates = [
        ("a", "The promoter shall refund the amount with interest on demand."),
        ("b", "Volcanoes erupt when magma rises through the crust."),
    ]
    scores = [score for _doc_id, score in rr.rerank("refund of amount by promoter", candidates)]
    assert scores == sorted(scores, reverse=True)
