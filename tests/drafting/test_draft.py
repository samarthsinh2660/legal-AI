"""One thread becomes one document, in one model call.

The model returns structure; the template carries the letterhead frame, the
formal opening and the numbering, so a two-page notice costs about 500
words of generation rather than the whole document.
"""

import json

import pytest

from legal_ai import drafting
from legal_ai.drafting import draft

RETRIEVED = {"act:2189:sec-138", "act:2189:sec-142"}

REPLY = {
    "subject": "Notice under Section 138 of the Negotiable Instruments Act, 1881",
    "recipient": {"name": "Mr. Rohan Malhotra", "address": "B-14, Green Park, Delhi"},
    "sender": {"name": "Mr. Arjun Verma", "address": "44, Nizamuddin East, Delhi"},
    "facts": ["You issued cheque no. 0472913 in favour of my client for {{amount}}."],
    "legal_grounds": [
        {"text": "Dishonour is an offence.", "authority": "act:2189:sec-138"}
    ],
    "demand": {"what": "pay my client {{amount}}", "within_days": 15,
               "from": "receipt of this notice"},
    "consequence": "Criminal prosecution will follow.",
    "annexures": ["Copy of the cheque"],
    "needs_input": [],
    "warnings": [],
}


def _stub(monkeypatch, payload):
    monkeypatch.setattr(
        drafting, "generate",
        lambda prompt, **kw: json.dumps(payload) if isinstance(payload, dict) else payload,
    )


def _draft(**kw):
    return draft("s138_demand_notice", "matter", "conversation", "law", RETRIEVED, **kw)


def test_a_reply_becomes_a_structure(monkeypatch):
    _stub(monkeypatch, REPLY)
    result = _draft()

    assert result.failures == ()
    assert result.structure.recipient.name == "Mr. Rohan Malhotra"
    assert len(result.structure.facts) == 1
    assert result.structure.grounds[0].authority == "act:2189:sec-138"


def test_the_amount_comes_from_the_record(monkeypatch):
    _stub(monkeypatch, REPLY)
    result = _draft(values={"amount": "Rs. 5,00,000/-"})

    assert result.structure.values["amount"] == "Rs. 5,00,000/-"


def test_a_fabricated_citation_is_reported(monkeypatch):
    """The worst failure this feature has, so it must not render."""
    payload = dict(REPLY, legal_grounds=[{"text": "X", "authority": "act:9999:sec-1"}])
    _stub(monkeypatch, payload)

    assert any("not retrieved" in f for f in _draft().failures)


def test_a_fenced_reply_is_read(monkeypatch):
    _stub(monkeypatch, "```json\n" + json.dumps(REPLY) + "\n```")

    assert _draft().failures == ()


def test_an_unreadable_reply_is_reported_not_raised(monkeypatch):
    _stub(monkeypatch, "not json at all")
    result = _draft()

    assert result.structure is None
    assert any("could not be read" in f for f in result.failures)


def test_an_unreachable_model_is_reported_not_raised(monkeypatch):
    def boom(prompt, **kw):
        raise RuntimeError("503")

    monkeypatch.setattr(drafting, "generate", boom)
    result = _draft()

    assert result.structure is None
    assert any("unreachable" in f for f in result.failures)


def test_an_unknown_document_type_never_reaches_the_model(monkeypatch):
    def boom(prompt, **kw):
        raise AssertionError("must not call a model for a type with no template")

    monkeypatch.setattr(drafting, "generate", boom)
    result = draft("not_a_type", "m", "c", "l", RETRIEVED)

    assert result.structure is None
    assert any("no template" in f for f in result.failures)


def test_a_missing_within_days_falls_back_to_the_statutory_fifteen(monkeypatch):
    _stub(monkeypatch, dict(REPLY, demand={"what": "pay {{amount}}"}))

    assert _draft().structure.demand.within_days == 15


def test_one_model_call_per_document(monkeypatch):
    calls = []
    monkeypatch.setattr(
        drafting, "generate",
        lambda prompt, **kw: calls.append(1) or json.dumps(REPLY),
    )
    _draft()

    assert len(calls) == 1


def test_the_draft_budget_is_its_own_not_the_summary_budget(monkeypatch):
    seen = {}
    monkeypatch.setattr(
        drafting, "generate",
        lambda prompt, **kw: seen.update(kw) or json.dumps(REPLY),
    )
    _draft()

    from legal_ai.config import DEFAULT_CONFIG
    assert seen["max_output_tokens"] == DEFAULT_CONFIG.draft_model_max_tokens
