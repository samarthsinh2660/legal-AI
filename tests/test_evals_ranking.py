import pytest

from evals.evaluators.ranking import first_relevant_rank, mean_reciprocal_rank, recall_at_k


def test_first_relevant_rank_is_one_based():
    # Rank 1 means "top hit", not "index 0" -- MRR of a top hit must be 1.0.
    assert first_relevant_rank(["a", "b", "c"], {"a"}) == 1
    assert first_relevant_rank(["a", "b", "c"], {"c"}) == 3


def test_first_relevant_rank_is_none_when_absent():
    assert first_relevant_rank(["a", "b"], {"z"}) is None


def test_first_relevant_rank_takes_the_earliest_of_several_correct_answers():
    # Some questions have more than one right answer (near-duplicate
    # provisions across Acts); credit the best-ranked one.
    assert first_relevant_rank(["a", "b", "c"], {"c", "b"}) == 2


def test_first_relevant_rank_of_empty_results_is_none():
    assert first_relevant_rank([], {"a"}) is None


def test_mean_reciprocal_rank_averages_inverse_ranks():
    # 1/1 + 1/2 + 1/4 over three questions.
    assert mean_reciprocal_rank([1, 2, 4]) == pytest.approx((1 + 0.5 + 0.25) / 3)


def test_mean_reciprocal_rank_scores_a_miss_as_zero():
    assert mean_reciprocal_rank([1, None]) == pytest.approx(0.5)


def test_mean_reciprocal_rank_of_nothing_is_zero():
    assert mean_reciprocal_rank([]) == 0.0


def test_recall_at_k_counts_ranks_within_k():
    assert recall_at_k([1, 3, 11, None], k=5) == pytest.approx(0.5)


def test_recall_at_k_boundary_is_inclusive():
    assert recall_at_k([5], k=5) == 1.0
    assert recall_at_k([6], k=5) == 0.0


def test_recall_at_k_of_nothing_is_zero():
    assert recall_at_k([], k=10) == 0.0
