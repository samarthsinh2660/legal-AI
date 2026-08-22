"""Coverage metrics -- for questions whose answer is a SET of provisions.

`ranking.py` answers "where is the right document". That is the wrong
question for research: "my builder is three years late" is answered by the
RERA refund provision *and* the allottee's rights *and* which forum hears
it. Finding one of four is not four-fifths of an answer, and a rank-based
metric cannot say so.

Coverage is what a multi-angle benchmark measures, and it is the only metric
that can show whether decomposing a question into angles helps.
"""

from __future__ import annotations

from typing import Iterable


def coverage_at_k(ranked_ids: list[str], expected_ids: Iterable[str], k: int) -> float:
    """Fraction of the expected provisions found in the top k."""
    expected = set(expected_ids)
    if not expected:
        return 0.0
    return len(expected & set(ranked_ids[:k])) / len(expected)


def mean_coverage(coverages: Iterable[float]) -> float:
    values = list(coverages)
    return sum(values) / len(values) if values else 0.0


def complete_rate(coverages: Iterable[float]) -> float:
    """Fraction of questions answered *completely*.

    Harsher than mean coverage and closer to what a user experiences: an
    answer missing one of three remedies is a partly wrong answer, not a
    two-thirds-right one.
    """
    values = list(coverages)
    if not values:
        return 0.0
    return sum(1 for value in values if value >= 1.0) / len(values)
