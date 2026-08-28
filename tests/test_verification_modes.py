"""Verification level -- what changes between quick and verified, and what
must not.

Two invariants, and they are the reason a reader can trust the cheaper mode:

  1. The answer body is identical in both. Verified adds annotation; it
     never rewrites, softens or removes what was said.
  2. A run that asks for verified and cannot get it says so. It never
     returns quick output wearing a verified label.

Both are properties that decay silently the moment the two paths diverge in
code, which is why they are tested rather than documented.
"""

import json
from datetime import datetime, timezone

import pytest

from legal_ai.graph.build import build_research_graph
from legal_ai.schemas.evidence import Evidence, Provenance, SourceRef
from legal_ai.schemas.verification import Claim, Verdict

REAL = "act:2158:sec-18"
QUESTION = "what is the punishment for murder"


def _retrieved(document_id: str = REAL) -> Evidence:
    """Evidence on the findings channel.

    Seeded because groundedness restricts support to what this thread
    actually retrieved. Without it every claim is refused at stage 2 as
    "never retrieved" -- correct behaviour, but it settles the claim before
    the mode being tested can matter.
    """
    return Evidence(
        content="Return of amount and compensation.",
        document_id=document_id,
        provenance=Provenance(
            source=SourceRef(name="India Code", url="https://x", source_type="primary"),
            retrieved_at=datetime(2026, 8, 28, tzinfo=timezone.utc),
            licence="GoI",
            attribution_required=False,
        ),
    )


@pytest.fixture
def analyst_returns_a_paraphrase(monkeypatch):
    """A claim nothing mechanical can settle, so the mode actually matters."""
    monkeypatch.setattr(
        "legal_ai.graph.nodes.analyst",
        lambda state: {"claims": [Claim("a buyer may recover money", (REAL,))]},
    )


@pytest.fixture
def verifier_says_supported(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "legal_ai.agents.verifier.generate",
        lambda prompt, **kw: calls.append(prompt) or json.dumps(
            {"verdicts": [{"n": 1, "verdict": "SUPPORTED", "why": "ok"}]}
        ),
    )
    return calls


def test_the_answer_body_is_identical_in_both_modes(
    analyst_returns_a_paraphrase, verifier_says_supported
):
    """The invariant behind the whole design.

    If turning verification on changed the substance of the answer, a
    reader would be choosing between two different opinions of the law
    based on what they paid. Verification is an audit layer over an answer,
    never a second author of it.
    """
    graph = build_research_graph()
    seed = {"question": QUESTION, "findings": [_retrieved()]}
    quick = graph.invoke({**seed, "verification_level": "quick"})
    verified = graph.invoke({**seed, "verification_level": "verified"})

    assert quick["draft_answer"].lede == verified["draft_answer"].lede
    assert quick["draft_answer"].key_elements == verified["draft_answer"].key_elements
    assert quick["draft_answer"].citations == verified["draft_answer"].citations


def test_only_the_verified_run_spends_a_model_call(
    analyst_returns_a_paraphrase, verifier_says_supported
):
    graph = build_research_graph()

    seed = {"question": QUESTION, "findings": [_retrieved()]}

    graph.invoke({**seed, "verification_level": "quick"})
    assert verifier_says_supported == []

    graph.invoke({**seed, "verification_level": "verified"})
    assert len(verifier_says_supported) == 1


def test_the_quick_mode_marks_an_unchecked_claim_rather_than_approving_it(
    analyst_returns_a_paraphrase, verifier_says_supported
):
    # A claim nobody checked must not read like one that passed.
    result = build_research_graph().invoke(
        {"question": QUESTION, "findings": [_retrieved()], "verification_level": "quick"}
    )
    report = result["verification_report"]

    assert report.verdicts[0].verdict is Verdict.INSUFFICIENT_EVIDENCE
    assert report.verdicts[0].stage == "skipped"


def test_a_verified_run_that_cannot_verify_does_not_pretend_it_did(
    analyst_returns_a_paraphrase, monkeypatch
):
    """No silent downgrade.

    Silent degradation is the most common defect this project has produced:
    .env never loaded, token caps starving answers, extraction failure
    indistinguishable from an empty document. A verification badge that can
    appear without verification having happened would be the worst instance
    of that pattern, not the least.
    """
    from legal_ai.llm.client import AllModelsUnavailable

    def _dead(prompt, **kw):
        raise AllModelsUnavailable("every model failed")

    monkeypatch.setattr("legal_ai.agents.verifier.generate", _dead)

    with pytest.raises(AllModelsUnavailable):
        build_research_graph().invoke(
            {"question": QUESTION, "findings": [_retrieved()],
             "verification_level": "verified"}
        )


def test_the_cheap_mode_still_refuses_a_fabricated_citation(monkeypatch):
    # Cheaper means less checking effort, never no integrity.
    monkeypatch.setattr(
        "legal_ai.graph.nodes.analyst",
        lambda state: {"claims": [Claim("invented", ("act:9999:sec-nope",))]},
    )
    result = build_research_graph().invoke(
        {"question": QUESTION, "verification_level": "quick"}
    )

    assert result["verification_report"].verdicts[0].stage == "reference"
    assert "act:9999:sec-nope" not in result["answer"]


def test_an_unverifiable_claim_is_not_reported_as_a_finding_against_it(monkeypatch):
    """UNSUPPORTED is a finding; INSUFFICIENT_EVIDENCE is a gap in our shelf.

    The claim cites a real section this thread never retrieved. It DOES
    belong in the re-research set -- another pass can fetch the document,
    which is exactly what re-research is for -- but it must never reach the
    reader as "not supported", which would say we checked and found
    against them.

    An earlier version of this test asserted the opposite, on the reasoning
    that re-researching evidence we do not hold cannot help. That is false
    for a document we simply did not retrieve.
    """
    monkeypatch.setattr(
        "legal_ai.graph.nodes.analyst",
        lambda state: {"claims": [Claim("cites something unread", (REAL,))]},
    )
    result = build_research_graph().invoke(
        {"question": QUESTION, "verification_level": "quick"}
    )
    report = result["verification_report"]
    answer = result["draft_answer"]

    # Whether the claim ends as "never retrieved" or as a quick-mode skip
    # depends on whether the re-research pass fetched the document, which
    # is a research outcome, not a verification guarantee. Measured:
    #
    #     pass 1   INSUFFICIENT_EVIDENCE | reference   (not retrieved)
    #     pass 2   INSUFFICIENT_EVIDENCE | skipped     (fetched, unchecked)
    #
    # Either way the verdict is INSUFFICIENT_EVIDENCE, and either way the
    # reader must not be told we found against the claim.
    assert report.verdicts[0].verdict is Verdict.INSUFFICIENT_EVIDENCE
    assert answer.needs_verification == ()
    assert "NOT supported by the retrieved sources" not in result["answer"]
