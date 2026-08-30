"""The four verdicts must reach the reader as four different things.

The failure this guards: `unsupported_texts` carries only UNSUPPORTED, so a
claim marked INSUFFICIENT_EVIDENCE fell through to `key_elements` and
rendered as a plain, verified-looking claim. In quick mode -- the default --
every paraphrase gets that verdict, so unchecked claims were being presented
as checked. Building the distinction and not rendering it is the same as not
building it.
"""

from legal_ai.agents.draft import build_answer, render
from legal_ai.schemas.answer import AnalysisResult
from legal_ai.schemas.verification import (
    Claim,
    ClaimVerdict,
    Verdict,
    VerificationReport,
)

SUPPORTED = Claim("a promoter must refund on demand", ("act:1",))
PARTIAL = Claim("a promoter must refund automatically", ("act:1",))
AGAINST = Claim("a promoter faces imprisonment", ("act:1",))
UNCHECKED = Claim("a buyer may sue in Gujarat", ("act:1",))


def _report(*pairs):
    return VerificationReport(verdicts=[
        ClaimVerdict(claim, verdict, "because", "semantic") for claim, verdict in pairs
    ])


def _answer(*pairs):
    claims = tuple(claim for claim, _ in pairs)
    return build_answer("q", AnalysisResult(claims=claims, lede="L"), [],
                        report=_report(*pairs))


def test_each_verdict_lands_in_its_own_bucket():
    answer = _answer(
        (SUPPORTED, Verdict.SUPPORTED),
        (PARTIAL, Verdict.PARTIALLY_SUPPORTED),
        (AGAINST, Verdict.UNSUPPORTED),
        (UNCHECKED, Verdict.INSUFFICIENT_EVIDENCE),
    )

    assert [c.text for c in answer.key_elements] == [SUPPORTED.text]
    assert answer.partially_supported == (PARTIAL.text,)
    assert answer.needs_verification == (AGAINST.text,)
    assert answer.unchecked == (UNCHECKED.text,)


def test_an_unchecked_claim_is_not_rendered_as_a_verified_one():
    # The bug: INSUFFICIENT_EVIDENCE fell through to key_elements and was
    # printed with its citation, indistinguishable from a checked claim.
    answer = _answer((UNCHECKED, Verdict.INSUFFICIENT_EVIDENCE))
    text = render(answer)

    assert answer.key_elements == ()
    assert f"- {UNCHECKED.text} [act:1]" not in text
    assert UNCHECKED.text in text


def test_not_checked_reads_differently_from_not_supported():
    """The distinction the whole phase exists for.

    "We did not look" must not read as "we looked and found against you".
    """
    answer = _answer(
        (AGAINST, Verdict.UNSUPPORTED),
        (UNCHECKED, Verdict.INSUFFICIENT_EVIDENCE),
    )
    text = render(answer)

    assert "NOT supported by the retrieved sources" in text
    assert "Not checked" in text
    assert text.index("NOT supported") != text.index("Not checked")


def test_the_unchecked_heading_blames_our_corpus_not_the_claim():
    # Worded as a limit on us. With a few thousand judgments against an
    # Indian corpus in the crores, absence of evidence is the normal
    # condition, and phrasing it as a finding would be a claim we cannot
    # support.
    text = render(_answer((UNCHECKED, Verdict.INSUFFICIENT_EVIDENCE)))

    assert "sources searched" in text
    assert "verify independently" in text


def test_nothing_is_deleted_whatever_the_verdict():
    answer = _answer(
        (SUPPORTED, Verdict.SUPPORTED),
        (PARTIAL, Verdict.PARTIALLY_SUPPORTED),
        (AGAINST, Verdict.UNSUPPORTED),
        (UNCHECKED, Verdict.INSUFFICIENT_EVIDENCE),
    )
    text = render(answer)

    for claim in (SUPPORTED, PARTIAL, AGAINST, UNCHECKED):
        assert claim.text in text


def test_only_supported_claims_contribute_citations():
    # A source cited only by a claim we could not stand behind must not
    # appear in the citation list as though it backed the answer.
    answer = build_answer(
        "q",
        AnalysisResult(claims=(AGAINST,), lede="L"),
        [],
        report=_report((AGAINST, Verdict.UNSUPPORTED)),
    )

    assert answer.citations == ()


def test_an_answer_with_unchecked_claims_is_not_complete():
    # However true they may turn out to be, they were not checked.
    answer = _answer((SUPPORTED, Verdict.SUPPORTED),
                     (UNCHECKED, Verdict.INSUFFICIENT_EVIDENCE))

    assert answer.is_complete is False


def test_a_fully_supported_answer_is_complete_and_carries_no_warnings():
    # The control: without this, a test asserting the warnings appear would
    # pass on a renderer that printed them unconditionally.
    answer = _answer((SUPPORTED, Verdict.SUPPORTED))
    text = render(answer)

    assert answer.is_complete is True
    assert "NOT supported" not in text
    assert "Not checked" not in text
    assert "only in part" not in text


def test_the_old_text_only_caller_still_works():
    # Callers holding only claim texts predate the report and must keep
    # working; those texts always meant a finding against the claim.
    answer = build_answer(
        "q", AnalysisResult(claims=(AGAINST,), lede="L"), [],
        unsupported=(AGAINST.text,),
    )

    assert answer.needs_verification == (AGAINST.text,)


def test_a_claim_citing_nothing_is_flagged_even_with_no_report():
    # Nothing for a verifier to have checked.
    naked = Claim("the law says so", ())
    answer = build_answer("q", AnalysisResult(claims=(naked,), lede="L"), [])

    assert answer.needs_verification == (naked.text,)
