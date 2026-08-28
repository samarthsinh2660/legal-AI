"""The draft renderer: where the verifier's result becomes visible."""

from datetime import datetime, timezone

from legal_ai.agents.draft import build_answer, render
from legal_ai.schemas.answer import AnalysisResult, DraftAnswer
from legal_ai.schemas.evidence import Evidence, Provenance, SourceRef
from legal_ai.schemas.verification import Claim


def _evidence(doc_id, doc_type):
    return Evidence(
        content="text", document_id=doc_id, document_type=doc_type,
        provenance=Provenance(
            source=SourceRef(name="x", url="https://x", source_type="primary"),
            retrieved_at=datetime(2026, 8, 26, tzinfo=timezone.utc),
            licence="GoI", attribution_required=False,
        ),
    )


EVIDENCE = [
    _evidence("act:2158:sec-18", "section"),
    _evidence("judgment:ik-149094324", "judgment"),
]
GROUNDED = Claim("promoter must refund with interest", ("act:2158:sec-18",))
ALSO = Claim("the leading authority is Newtech", ("judgment:ik-149094324",))


def test_no_model_is_involved():
    # The inputs are already structured. Re-rendering them through a model
    # would only give it a chance to drop a citation.
    import inspect

    import legal_ai.agents.draft as draft

    assert "generate" not in inspect.getsource(draft)


def test_supported_claims_become_key_elements():
    answer = build_answer("q", AnalysisResult(claims=(GROUNDED,)), EVIDENCE)
    assert answer.key_elements == (GROUNDED,)
    assert answer.needs_verification == ()
    assert answer.is_complete


def test_an_unsupported_claim_is_flagged_not_deleted():
    # A reader who cannot see that something was dropped cannot tell a
    # short answer from an incomplete one.
    answer = build_answer(
        "q", AnalysisResult(claims=(GROUNDED,)), EVIDENCE,
        unsupported=(GROUNDED.text,),
    )
    assert answer.key_elements == ()
    assert answer.needs_verification == (GROUNDED.text,)
    assert not answer.is_complete


def test_a_claim_citing_nothing_is_unsupported_even_without_the_verifier():
    # There is nothing for the verifier to have checked, so it does not
    # need to have run for this to be unsupported.
    answer = build_answer("q", AnalysisResult(claims=(Claim("bare assertion"),)), EVIDENCE)
    assert answer.needs_verification == ("bare assertion",)


def test_law_and_judgments_are_separated():
    # A lawyer uses a provision and an authority differently, so the screen
    # must not blend them into one list.
    answer = build_answer("q", AnalysisResult(claims=(GROUNDED, ALSO)), EVIDENCE)
    assert answer.applicable_law == ("act:2158:sec-18",)
    assert answer.key_judgments == ("judgment:ik-149094324",)


def test_citations_cover_every_supported_claim():
    answer = build_answer("q", AnalysisResult(claims=(GROUNDED, ALSO)), EVIDENCE)
    assert set(answer.citations) == {"act:2158:sec-18", "judgment:ik-149094324"}


def test_an_unsupported_claim_contributes_no_citation():
    # Citing a source for a claim we could not ground would be the worst of
    # both: unverified content wearing a verified-looking reference.
    answer = build_answer(
        "q", AnalysisResult(claims=(GROUNDED,)), EVIDENCE, unsupported=(GROUNDED.text,)
    )
    assert answer.citations == ()


def test_the_disclaimer_is_always_present():
    assert build_answer("q", AnalysisResult(), []).disclaimer
    assert "not legal advice" in build_answer("q", AnalysisResult(), []).disclaimer


def test_rendering_marks_the_unsupported_section():
    """The heading was "Could not be verified", which conflated two states.

    A claim the evidence contradicts and a claim nobody checked are
    different things, and the second is our normal condition against an
    Indian corpus in the crores. They now render under separate headings;
    this covers the finding-against one.
    """
    answer = build_answer(
        "q", AnalysisResult(lede="Short answer.", claims=(GROUNDED, Claim("shaky"))),
        EVIDENCE,
    )
    text = render(answer)
    assert "Short answer." in text
    assert "act:2158:sec-18" in text
    assert "NOT supported by the retrieved sources" in text
    assert "shaky" in text


def test_rendering_an_empty_analysis_still_carries_the_disclaimer():
    assert "not legal advice" in render(build_answer("q", AnalysisResult(), []))
