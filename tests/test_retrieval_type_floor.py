"""A provision must not be crowded off the page by judgments.

Measured 2026-08-29 on the versioned 50-question set, whole corpus:

    no interleave    MRR 0.282   recall@5 42%   recall@10 54%
    interleaved      MRR 0.308   recall@5 52%   recall@10 68%

The corpus went from 18 judgments to 10,505, and judgments now fill the top
of the list for questions whose answer is a section. They are not junk --
on a RERA question the judgments outranking s.18 were Laureate Buildwell,
Ireo Grace and Newtech Promoters, the leading authorities on the point. The
defect is one-sidedness: a reader asking what the law says needs the
provision AND the cases, and got only cases.

Interleaving serves both questions instead of guessing between them, which
is why there is no intent classifier on the hot path.
"""

from legal_ai.retrieval.type_floor import apply_type_floor

TYPES = {
    "j1": "judgment", "j2": "judgment", "j3": "judgment", "j4": "judgment",
    "s1": "section", "s2": "section", "a1": "act",
}


def test_the_best_statute_surfaces_instead_of_trailing_the_judgments():
    ranked = ["j1", "j2", "j3", "j4", "s1"]
    assert apply_type_floor(ranked, TYPES, limit=4) == ["j1", "s1", "j2", "j3"]


def test_the_top_result_keeps_rank_one():
    """Retrieval's strongest answer is not demoted for balance."""
    ranked = ["j1", "j2", "s1"]
    assert apply_type_floor(ranked, TYPES, limit=3)[0] == "j1"

    ranked = ["s1", "j1", "j2"]
    assert apply_type_floor(ranked, TYPES, limit=3)[0] == "s1"


def test_each_kind_keeps_its_own_order():
    ranked = ["j1", "j2", "j3", "s1", "s2"]
    result = apply_type_floor(ranked, TYPES, limit=5)
    assert [i for i in result if i.startswith("j")] == ["j1", "j2", "j3"]
    assert [i for i in result if i.startswith("s")] == ["s1", "s2"]


def test_a_list_of_one_kind_is_untouched():
    """Nothing to interleave is not a reason to reorder or to drop."""
    ranked = ["j1", "j2", "j3"]
    assert apply_type_floor(ranked, TYPES, limit=2) == ["j1", "j2"]
    ranked = ["s1", "s2"]
    assert apply_type_floor(ranked, TYPES, limit=2) == ["s1", "s2"]


def test_acts_count_as_statute():
    ranked = ["j1", "j2", "a1"]
    assert apply_type_floor(ranked, TYPES, limit=3) == ["j1", "a1", "j2"]


def test_nothing_is_invented_or_lost_within_the_limit():
    ranked = ["j1", "j2", "s1", "j3", "s2"]
    result = apply_type_floor(ranked, TYPES, limit=5)
    assert sorted(result) == sorted(ranked)


def test_a_short_list_is_returned_whole():
    assert apply_type_floor(["j1", "s1"], TYPES, limit=10) == ["j1", "s1"]


def test_unknown_types_are_treated_as_non_statute():
    """An id whose type we could not read must not be promoted as a
    provision -- that would put an unknown document in the Rule slot."""
    ranked = ["x1", "j1", "s1"]
    result = apply_type_floor(ranked, {"j1": "judgment", "s1": "section"}, limit=3)
    assert result[0] == "x1"
    assert "s1" in result


def test_empty():
    assert apply_type_floor([], {}, limit=5) == []
