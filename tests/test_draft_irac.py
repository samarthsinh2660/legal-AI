"""IRAC is a regrouping of the verified answer, not a second draft of it.

The temptation is to hand the claims to a model and ask for an IRAC essay.
That would put un-verified prose in front of the reader after Phase 6 spent
the whole pipeline making every sentence checkable, and give the model a
chance to drop a citation on the way -- the exact reason draft.py assembles
rather than generates.

So: no model call. Issue is the question, Rule is what the statutes say,
Analysis is what the courts held, Conclusion is the lede. Every line traces
to a claim that already passed verification.
"""

from datetime import datetime, timezone

from legal_ai.agents.draft import build_answer, render_irac
from legal_ai.schemas.answer import AnalysisResult
from legal_ai.schemas.evidence import Evidence, Provenance, SourceRef
from legal_ai.schemas.verification import Claim


def _ev(doc_id: str, doc_type: str) -> Evidence:
    return Evidence(
        content="x", document_id=doc_id, document_type=doc_type,
        provenance=Provenance(
            source=SourceRef(name="x", url="https://x", source_type="primary"),
            retrieved_at=datetime(2026, 8, 29, tzinfo=timezone.utc),
            licence="GoI", attribution_required=False,
        ),
    )


EVIDENCE = [_ev("act:1:sec-18", "section"), _ev("judgment:j1", "judgment")]
STATUTE_CLAIM = Claim("the promoter must refund on demand", ("act:1:sec-18",))
JUDGMENT_CLAIM = Claim("the Court read that as unconditional", ("judgment:j1",))


def _answer(*claims, unsupported=()):
    return build_answer(
        "can I get a refund?",
        AnalysisResult(claims=tuple(claims), lede="Yes, on demand."),
        EVIDENCE,
        unsupported=unsupported,
    )


def test_the_question_is_the_issue():
    text = render_irac(_answer(STATUTE_CLAIM))
    assert "can I get a refund?" in text


def test_statutes_are_the_rule_and_judgments_the_analysis():
    text = render_irac(_answer(STATUTE_CLAIM, JUDGMENT_CLAIM))
    rule = text.index("Rule")
    analysis = text.index("Analysis")
    assert rule < text.index("the promoter must refund on demand") < analysis
    assert analysis < text.index("the Court read that as unconditional")


def test_the_lede_is_the_conclusion():
    text = render_irac(_answer(STATUTE_CLAIM))
    assert text.index("Conclusion") < text.index("Yes, on demand.")


def test_an_unsupported_claim_does_not_appear_as_rule_or_analysis():
    """It failed verification. IRAC must not be a second door into the
    answer for a claim the front door rejected."""
    text = render_irac(_answer(STATUTE_CLAIM, unsupported=(STATUTE_CLAIM.text,)))
    body = text[: text.index("Conclusion")]
    assert STATUTE_CLAIM.text not in body


def test_an_unsupported_claim_is_still_shown_somewhere():
    """Dropping it silently would leave a short answer indistinguishable
    from an incomplete one -- the same rule the rest of draft.py follows."""
    text = render_irac(_answer(STATUTE_CLAIM, unsupported=(STATUTE_CLAIM.text,)))
    assert STATUTE_CLAIM.text in text


def test_no_claims_still_renders_the_question():
    text = render_irac(_answer())
    assert "can I get a refund?" in text


def test_every_claim_keeps_its_citations():
    text = render_irac(_answer(STATUTE_CLAIM, JUDGMENT_CLAIM))
    assert "act:1:sec-18" in text
    assert "judgment:j1" in text


def test_the_disclaimer_survives():
    text = render_irac(_answer(STATUTE_CLAIM))
    assert "not legal advice" in text
