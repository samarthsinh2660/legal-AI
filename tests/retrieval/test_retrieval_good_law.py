"""Is this case still good law?

Three answers, and the third is the whole point. "Nothing overrules it" and
"we have not checked" are different facts, and a corpus that resolves a
fraction of the citations it extracts is in the second state far more often
than the first. Rendering them alike would be the most dangerous defect this
system could ship: a confident green light nobody verified.
"""

from legal_ai.agents.treatment import Treatment
from legal_ai.retrieval.good_law import GoodLaw, assess_good_law


def test_an_overruling_makes_it_doubted():
    result = assess_good_law([("j-later", Treatment.OVERRULED)])
    assert result.status is GoodLaw.DOUBTED
    assert result.overruled_by == ("j-later",)


def test_followed_and_considered_leave_it_standing():
    result = assess_good_law([
        ("j1", Treatment.FOLLOWED), ("j2", Treatment.CONSIDERED),
    ])
    assert result.status is GoodLaw.NO_NEGATIVE_TREATMENT


def test_distinguishing_does_not_doubt_it():
    """A distinguished case is still good law on its own facts."""
    result = assess_good_law([("j1", Treatment.DISTINGUISHED)])
    assert result.status is GoodLaw.NO_NEGATIVE_TREATMENT


def test_nothing_citing_it_is_not_a_clean_bill():
    """No citing judgments means our corpus holds none -- not that none
    exist. This is the ordinary case and must not read as verified."""
    assert assess_good_law([]).status is GoodLaw.NOT_CHECKED


def test_unclassified_citations_are_not_a_clean_bill():
    result = assess_good_law([("j1", Treatment.NOT_CHECKED)])
    assert result.status is GoodLaw.NOT_CHECKED


def test_one_unclassified_citation_taints_the_whole_answer():
    """If any citing judgment was never classified, an overruling could be
    hiding in it, so the answer cannot be NO_NEGATIVE_TREATMENT."""
    result = assess_good_law([
        ("j1", Treatment.FOLLOWED), ("j2", Treatment.NOT_CHECKED),
    ])
    assert result.status is GoodLaw.NOT_CHECKED


def test_an_overruling_beats_an_unclassified_citation():
    """A known overruling is a finding; not knowing about others does not
    soften it."""
    result = assess_good_law([
        ("j1", Treatment.NOT_CHECKED), ("j2", Treatment.OVERRULED),
    ])
    assert result.status is GoodLaw.DOUBTED


def test_every_overruling_judgment_is_named():
    result = assess_good_law([
        ("j1", Treatment.OVERRULED), ("j2", Treatment.OVERRULED),
    ])
    assert set(result.overruled_by) == {"j1", "j2"}


def test_only_doubted_is_a_warning():
    assert assess_good_law([("j", Treatment.OVERRULED)]).is_a_warning
    assert not assess_good_law([("j", Treatment.FOLLOWED)]).is_a_warning
    assert not assess_good_law([]).is_a_warning
