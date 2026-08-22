"""Ranking metrics -- pure functions over ranked document-id lists.

Deliberately free of database, model and file access so they can be tested
directly. A measuring instrument that cannot itself be verified is worse
than no instrument, because its numbers still get believed.

A rank is 1-based; None means the correct answer was not returned at all.
"""

from __future__ import annotations

from typing import Iterable, Optional


def first_relevant_rank(ranked_ids: list[str], expected_ids: Iterable[str]) -> Optional[int]:
    """1-based rank of the earliest correct answer, or None if absent.

    A question may have several correct answers -- near-duplicate provisions
    exist across Acts -- and the best-ranked one is what counts.
    """
    expected = set(expected_ids)
    for rank, document_id in enumerate(ranked_ids, start=1):
        if document_id in expected:
            return rank
    return None


def mean_reciprocal_rank(ranks: Iterable[int | None]) -> float:
    """Mean of 1/rank, scoring a miss as 0.

    MRR is dominated by the top few positions: rank 1 scores 1.0 while rank
    10 scores 0.1. It answers "is the right answer at the top", which is a
    different question from recall@k's "is it in the list at all".
    """
    values = list(ranks)
    if not values:
        return 0.0
    return sum(0.0 if rank is None else 1.0 / rank for rank in values) / len(values)


def recall_at_k(ranks: Iterable[int | None], k: int) -> float:
    """Fraction of questions whose correct answer landed in the top k."""
    values = list(ranks)
    if not values:
        return 0.0
    return sum(1 for rank in values if rank is not None and rank <= k) / len(values)
