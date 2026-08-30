"""Ranking judgments by how much authority they carry.

Two different things are measured and deliberately not blended: how often
other courts cite a judgment (influence), and how many judges sat on it
(binding force). A five-judge bench binds a two-judge bench whether or not
anyone has cited it yet, so collapsing both into one number would hide
which of the two is driving an ordering.
"""

from __future__ import annotations

from legal_ai.retrieval.authority import Authority, rank_by_authority


def a(doc_id: str, citations: int = 0, bench: int | None = None) -> Authority:
    return Authority(document_id=doc_id, citation_count=citations, bench_size=bench)


def test_more_cited_ranks_higher():
    ranked = rank_by_authority([a("low", 2), a("high", 40)])
    assert [x.document_id for x in ranked] == ["high", "low"]


def test_bench_breaks_a_citation_tie():
    """Equally cited, the larger bench is the stronger authority."""
    ranked = rank_by_authority([a("two", 5, bench=2), a("five", 5, bench=5)])
    assert [x.document_id for x in ranked] == ["five", "two"]


def test_citations_outrank_bench():
    """Bench is a tie-breaker, not the primary key. A Constitution Bench
    nobody has cited is not yet the leading authority on a question, and
    presenting it as one would bury the case practitioners actually follow."""
    ranked = rank_by_authority([a("cited", 30, bench=2), a("big-bench", 1, bench=5)])
    assert [x.document_id for x in ranked] == ["cited", "big-bench"]


def test_unknown_bench_does_not_count_as_small():
    """bench_size is None when the header would not parse. Treating that as
    1 would push unparsed judgments below every parsed one for no reason."""
    ranked = rank_by_authority([a("unknown", 5, bench=None), a("single", 5, bench=1)])
    assert [x.document_id for x in ranked] == ["single", "unknown"]
    assert ranked[1].bench_size is None


def test_stable_and_deterministic_on_full_ties():
    items = [a("b", 3, 2), a("a", 3, 2), a("c", 3, 2)]
    assert [x.document_id for x in rank_by_authority(items)] == ["a", "b", "c"]


def test_empty():
    assert rank_by_authority([]) == []


def test_uncited_judgments_are_kept_not_dropped():
    """Zero citations means our corpus holds nothing citing it -- which is
    the normal case for a thin corpus, not evidence the case is weak."""
    ranked = rank_by_authority([a("cited", 4), a("uncited", 0)])
    assert [x.document_id for x in ranked] == ["cited", "uncited"]
    assert len(ranked) == 2


def test_is_constitution_bench():
    assert a("x", bench=5).is_constitution_bench
    assert not a("x", bench=3).is_constitution_bench
    assert not a("x", bench=None).is_constitution_bench
