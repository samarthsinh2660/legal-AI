"""Stage 6 -- the semantic check, with the model stubbed.

These fix the contract, not the model's judgement: what happens to a claim
the verifier does not rule on, returns nonsense about, or answers with a
verdict it is not allowed to give. The model's actual accuracy is measured
by the eval, not asserted here.
"""

import json

import pytest

from legal_ai.schemas.verification import Claim, Verdict
from legal_ai.agents import verifier as module
from legal_ai.agents.verifier import check_support

SECTION = "The promoter shall return the amount received with interest."
SOURCES = {"act:1:sec-18": SECTION}
CLAIMS = [
    Claim("a promoter must refund with interest", ("act:1:sec-18",)),
    Claim("a promoter faces imprisonment", ("act:1:sec-18",)),
]


def _reply(monkeypatch, payload):
    monkeypatch.setattr(module, "generate", lambda *a, **k: json.dumps(payload))


def test_verdicts_are_returned_in_claim_order(monkeypatch):
    _reply(monkeypatch, {"verdicts": [
        {"n": 1, "verdict": "SUPPORTED", "why": "states it"},
        {"n": 2, "verdict": "UNSUPPORTED", "why": "no penalty in the text"},
    ]})
    verdicts, calls = check_support(CLAIMS, SOURCES)

    assert [v.verdict for v in verdicts] == [Verdict.SUPPORTED, Verdict.UNSUPPORTED]
    assert [v.claim.text for v in verdicts] == [c.text for c in CLAIMS]


def test_it_is_one_batched_call_for_every_claim(monkeypatch):
    calls = []
    monkeypatch.setattr(module, "generate", lambda *a, **k: calls.append(1) or json.dumps(
        {"verdicts": [{"n": 1, "verdict": "SUPPORTED"}, {"n": 2, "verdict": "SUPPORTED"}]}))

    _verdicts, reported = check_support(CLAIMS, SOURCES)

    assert len(calls) == 1
    assert reported == 1


def test_no_claims_makes_no_call(monkeypatch):
    monkeypatch.setattr(module, "generate", lambda *a, **k: pytest.fail("called"))
    assert check_support([], SOURCES) == ([], 0)


# ------------------------------------------------------- failing closed

def test_a_claim_the_verifier_skipped_is_unsupported_not_approved(monkeypatch):
    # Silence is not approval. A claim nobody ruled on must not read like
    # one that passed.
    _reply(monkeypatch, {"verdicts": [{"n": 1, "verdict": "SUPPORTED"}]})
    verdicts, _ = check_support(CLAIMS, SOURCES)

    assert verdicts[1].verdict is Verdict.UNSUPPORTED
    assert "no verdict" in verdicts[1].reason


def test_unreadable_json_fails_closed(monkeypatch):
    monkeypatch.setattr(module, "generate", lambda *a, **k: "I think claim 1 is fine!")
    verdicts, calls = check_support(CLAIMS, SOURCES)

    assert all(v.verdict is Verdict.UNSUPPORTED for v in verdicts)
    assert "unreadable" in verdicts[0].reason
    assert calls == 1


def test_an_unrecognised_verdict_label_is_not_an_approval(monkeypatch):
    _reply(monkeypatch, {"verdicts": [
        {"n": 1, "verdict": "PROBABLY_FINE"},
        {"n": 2, "verdict": "SUPPORTED"},
    ]})
    verdicts, _ = check_support(CLAIMS, SOURCES)

    assert verdicts[0].verdict is Verdict.UNSUPPORTED
    assert verdicts[1].verdict is Verdict.SUPPORTED


def test_the_model_may_not_return_insufficient_evidence(monkeypatch):
    # That verdict is a fact about retrieval, not a judgement. Allowing it
    # here would hand the model an escape hatch on the hard claims.
    _reply(monkeypatch, {"verdicts": [
        {"n": 1, "verdict": "INSUFFICIENT_EVIDENCE"},
        {"n": 2, "verdict": "SUPPORTED"},
    ]})
    verdicts, _ = check_support(CLAIMS, SOURCES)

    assert verdicts[0].verdict is Verdict.UNSUPPORTED
    assert verdicts[1].verdict is Verdict.SUPPORTED


def test_prose_around_the_json_is_tolerated(monkeypatch):
    monkeypatch.setattr(module, "generate", lambda *a, **k:
                        'Here you go:\n{"verdicts": [{"n": 1, "verdict": "SUPPORTED"}, '
                        '{"n": 2, "verdict": "UNSUPPORTED"}]}\nHope that helps.')
    verdicts, _ = check_support(CLAIMS, SOURCES)

    assert [v.verdict for v in verdicts] == [Verdict.SUPPORTED, Verdict.UNSUPPORTED]


# ------------------------------------------------------------- the prompt

def test_the_cited_text_is_put_in_front_of_the_model(monkeypatch):
    seen = {}
    monkeypatch.setattr(module, "generate", lambda prompt, **k: seen.update(p=prompt) or
                        json.dumps({"verdicts": [{"n": 1, "verdict": "SUPPORTED"},
                                                 {"n": 2, "verdict": "SUPPORTED"}]}))
    check_support(CLAIMS, SOURCES)

    assert SECTION in seen["p"]
    assert "act:1:sec-18" in seen["p"]


def test_a_missing_source_is_marked_rather_than_omitted(monkeypatch):
    # An absent document must not look like an empty one, or the model
    # would judge the claim against nothing and call it unsupported for
    # the wrong reason.
    seen = {}
    monkeypatch.setattr(module, "generate", lambda prompt, **k: seen.update(p=prompt) or
                        json.dumps({"verdicts": [{"n": 1, "verdict": "SUPPORTED"}]}))
    check_support([Claim("x", ("act:1:sec-99",))], {})

    assert "(text unavailable)" in seen["p"]


def test_the_prompt_forbids_answering_from_the_model_s_own_knowledge():
    """The failure this check exists for is a claim that is true in Indian
    law but not stated in the cited text. The answer being verified was
    itself model-written, so a verifier agreeing from memory verifies
    nothing -- it just asks the same model twice.
    """
    prompt = module._PROMPT.lower()

    assert "memory" in prompt
    assert "unsupported" in prompt
    # Stated as a consequence, not merely as a prohibition, so the rule
    # survives a reader who skims.
    assert "not stated in this text" in prompt


def test_the_prompt_defines_every_verdict_it_asks_for():
    # A label the model has to guess the meaning of is a label it will
    # apply inconsistently, which shows up as flip rate.
    for verdict in ("SUPPORTED", "PARTIALLY_SUPPORTED", "UNSUPPORTED"):
        assert verdict in module._PROMPT


def test_the_prompt_never_offers_insufficient_evidence_as_a_verdict():
    # Whether we retrieved material capable of settling a claim is a fact
    # about retrieval. Offering it here would hand the model an escape
    # hatch on exactly the hard claims.
    assert "INSUFFICIENT_EVIDENCE" not in module._PROMPT


def test_the_prompt_breaks_ties_toward_caution():
    # The costs are not symmetric: a wrongly flagged claim costs a second
    # look, a wrongly approved one is a false statement of law presented
    # as checked.
    assert "cautious" in module._PROMPT.lower()


def test_the_prompt_states_the_role_narrowly():
    # Without this a model answers the legal question instead of checking
    # the claim, which reads plausible and measures nothing.
    assert "not to answer the question" in module._PROMPT.lower()


def test_the_prompt_carries_worked_examples_for_the_partial_boundary():
    # SUPPORTED vs UNSUPPORTED is easy; the overstated-claim boundary is
    # where judgement actually varies, so it is shown rather than described.
    assert "PARTIALLY_SUPPORTED" in module._PROMPT
    assert "->" in module._PROMPT


def test_long_sources_are_truncated_so_a_judgment_cannot_blow_the_prompt(monkeypatch):
    seen = {}
    monkeypatch.setattr(module, "generate", lambda prompt, **k: seen.update(p=prompt) or
                        json.dumps({"verdicts": [{"n": 1, "verdict": "SUPPORTED"}]}))
    check_support([Claim("x", ("j:1",))], {"j:1": "A" * 50_000})

    assert len(seen["p"]) < 20_000
