"""How the good-law finding reaches a reader.

The dangerous version of this feature is a green tick. `NO_NEGATIVE_TREATMENT`
means "nothing in OUR corpus contradicts this", and our corpus holds 12,337
judgments against an Indian reports series in the crores. A reader who takes
that as "verified good law" will stop checking, which is the one outcome this
whole system exists to prevent.

So the wording carries the denominator, and the absence of a warning is never
itself rendered as reassurance.
"""

from legal_ai.agents.draft import render_good_law
from legal_ai.agents.treatment import Treatment
from legal_ai.retrieval.good_law import GoodLaw, assess_good_law


def test_an_overruling_is_stated_plainly():
    result = assess_good_law([("judgment:x", Treatment.OVERRULED)])
    text = render_good_law(result)
    assert "overrul" in text.lower()
    assert "judgment:x" in text


def test_a_clean_result_names_its_denominator():
    """Not 'good law' -- 'no negative treatment among the N we hold'."""
    result = assess_good_law([
        ("j1", Treatment.FOLLOWED), ("j2", Treatment.CONSIDERED),
    ])
    text = render_good_law(result)
    assert "2" in text
    assert "good law" not in text.lower()


def test_a_clean_result_never_claims_verification():
    result = assess_good_law([("j1", Treatment.FOLLOWED)])
    text = render_good_law(result).lower()
    for forbidden in ("verified", "confirmed", "still good law", "safe to rely"):
        assert forbidden not in text


def test_not_checked_says_so_rather_than_going_quiet():
    """Silence would read as 'nothing to report', which is reassurance we
    did not earn."""
    text = render_good_law(assess_good_law([]))
    assert text
    assert "not" in text.lower() or "no citing" in text.lower()


def test_an_unclassified_citation_does_not_render_as_clean():
    result = assess_good_law([
        ("j1", Treatment.FOLLOWED), ("j2", Treatment.NOT_CHECKED),
    ])
    assert result.status is GoodLaw.NOT_CHECKED
    assert "no negative treatment" not in render_good_law(result).lower()


def test_every_status_renders_something():
    for citing in ([], [("j", Treatment.FOLLOWED)], [("j", Treatment.OVERRULED)]):
        assert render_good_law(assess_good_law(citing)).strip()
