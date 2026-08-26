"""Analyst and draft in the graph -- and the verifier finally receiving claims.

Before this the verification node returned early on every run: nothing in
the codebase produced claims, so the groundedness check built in Phase 3
had never executed on anything.
"""

import json

import pytest

from legal_ai.graph import nodes
from legal_ai.schemas.answer import AnalysisResult
from legal_ai.schemas.verification import Claim
from tests.test_draft import EVIDENCE, GROUNDED


def _analyst_returns(monkeypatch, payload):
    monkeypatch.setattr(
        "legal_ai.agents.analyst.generate",
        lambda p, **kw: json.dumps(payload),
    )


def test_the_analyst_node_puts_claims_on_the_channel(monkeypatch):
    _analyst_returns(monkeypatch, {"lede": "L", "claims": [
        {"text": "refund with interest", "evidence_ids": ["act:2158:sec-18"]},
    ]})
    out = nodes.analyst({"question": "q", "findings": EVIDENCE})
    assert [c.text for c in out["claims"]] == ["refund with interest"]


def test_verification_no_longer_returns_early(monkeypatch):
    # The check exists since Phase 3 and had never run. With claims on the
    # channel it does.
    ran = {}

    def fake_check(claims, conn, available_ids=None):
        ran["claims"] = claims
        from legal_ai.verification.groundedness import GroundednessResult

        return GroundednessResult(grounded=list(claims), unsupported=[])

    monkeypatch.setattr("legal_ai.verification.groundedness.check_groundedness", fake_check)
    nodes.verification({"question": "q", "claims": [GROUNDED], "findings": EVIDENCE})
    assert ran["claims"] == [GROUNDED]


def test_the_draft_node_produces_a_structured_answer():
    out = nodes.draft({
        "question": "what are my options",
        "analysis": AnalysisResult(lede="You may claim a refund.", claims=(GROUNDED,)),
        "findings": EVIDENCE,
        "unsupported_claims": [],
    })
    answer = out["draft_answer"]
    assert answer.lede == "You may claim a refund."
    assert answer.applicable_law == ("act:2158:sec-18",)
    assert "act:2158:sec-18" in out["answer"]


def test_the_draft_node_no_longer_returns_a_stub():
    out = nodes.draft({"question": "q", "findings": [], "unsupported_claims": []})
    assert "[stub answer" not in out["answer"]
    assert "not legal advice" in out["answer"]


def test_an_unsupported_claim_reaches_the_reader_labelled():
    # The whole payoff for having a verifier: without this the reader sees
    # a grounded claim and an ungrounded one in the same font.
    out = nodes.draft({
        "question": "q",
        "analysis": AnalysisResult(claims=(GROUNDED,)),
        "findings": EVIDENCE,
        "unsupported_claims": [GROUNDED.text],
    })
    assert out["draft_answer"].needs_verification == (GROUNDED.text,)
    assert "Could not be verified" in out["answer"]


def test_a_question_still_costs_one_model_call(monkeypatch):
    # The Analyst replaces the supervisor's summarise call rather than
    # adding to it.
    calls = []
    monkeypatch.setattr(
        "legal_ai.agents.analyst.generate",
        lambda p, **kw: calls.append(1) or '{"claims": []}',
    )
    nodes.analyst({"question": "q", "findings": EVIDENCE})
    nodes.draft({"question": "q", "findings": EVIDENCE, "unsupported_claims": []})
    assert len(calls) == 1


def test_an_ungrounded_claim_reaches_the_final_answer_labelled(monkeypatch):
    """The whole reason the draft step exists, proven through the real graph.

    Research, analyst, verification and draft all run. A claim citing a
    document that does not exist must survive to the answer *marked*, not
    silently deleted and not presented like the grounded ones.
    """
    from legal_ai.graph.build import build_research_graph

    monkeypatch.setattr(
        "legal_ai.graph.nodes.analyst",
        lambda state: {
            "claims": [Claim("a fabricated holding", ("act:9999:sec-nope",))],
            "analysis": AnalysisResult(
                lede="Short answer.",
                claims=(Claim("a fabricated holding", ("act:9999:sec-nope",)),),
            ),
        },
    )
    result = build_research_graph().invoke({"question": "what is the punishment for murder"})

    assert result["unsupported_claims"] == ["a fabricated holding"]
    # Labelled in the text a reader actually sees.
    assert "Could not be verified" in result["answer"]
    assert "a fabricated holding" in result["answer"]
    # And it must not be dressed up with a citation.
    assert "act:9999:sec-nope" not in result["answer"]
    assert result["draft_answer"].is_complete is False


def test_a_grounded_run_produces_no_warning_section(monkeypatch):
    """The control: without this, a test asserting the warning appears would
    pass on a graph that printed the warning unconditionally."""
    from legal_ai.graph.build import build_research_graph

    grounded = Claim("promoter must refund", ("act:2158:sec-18",))
    monkeypatch.setattr(
        "legal_ai.graph.nodes.analyst",
        lambda state: {
            "claims": [grounded],
            "analysis": AnalysisResult(lede="Short answer.", claims=(grounded,)),
        },
    )
    # Deliberately not a builder/possession question: those trip the
    # clarification gate without a state, which halts the run before
    # verification and would make this pass for the wrong reason.
    result = build_research_graph().invoke({
        "question": "what is the punishment for murder",
        "findings": EVIDENCE,
    })
    assert result["unsupported_claims"] == []
    assert "Could not be verified" not in result["answer"]
    assert result["draft_answer"].is_complete is True
