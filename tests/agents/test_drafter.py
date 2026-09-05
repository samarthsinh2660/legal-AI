"""One conversation becomes one document, in one model call.

The model chooses what document the conversation calls for; the renderer
draws whatever sections it returns. There is no document type to pick.
"""

import json

from legal_ai.agents import drafter
from legal_ai.agents.drafter import draft

RETRIEVED = {"act:2189:sec-138", "act:2189:sec-142"}

REPLY = {
    "title": "NOTICE UNDER SECTION 138 OF THE NEGOTIABLE INSTRUMENTS ACT, 1881",
    "subject": "Dishonour of cheque no. 0472913",
    "addressed_to": "Mr. Rohan Malhotra",
    "on_behalf_of": "Mr. Arjun Verma",
    "sections": [
        {"heading": "FACTS",
         "paragraphs": [{"text": "You issued cheque no. 0472913.", "authorities": []}]},
        {"heading": "THE POSITION",
         "paragraphs": [{"text": "Dishonour is an offence.",
                         "authorities": ["act:2189:sec-138"]}]},
    ],
    "needs_input": [],
    "warnings": [],
}


def _stub(monkeypatch, payload):
    monkeypatch.setattr(
        drafter, "generate",
        lambda prompt, **kw: json.dumps(payload) if isinstance(payload, dict) else payload,
    )


def _draft():
    return draft("matter", "conversation", "law", RETRIEVED)


def test_a_reply_becomes_a_structure(monkeypatch):
    _stub(monkeypatch, REPLY)
    result = _draft()

    assert result.failures == ()
    assert result.structure.title.startswith("NOTICE UNDER SECTION 138")
    assert len(result.structure.sections) == 2
    assert result.structure.sections[1].paragraphs[0].authorities == ("act:2189:sec-138",)


def test_the_model_chooses_the_document(monkeypatch):
    """Nothing is passed in saying what to draft."""
    _stub(monkeypatch, dict(REPLY, title="LEGAL OPINION"))

    assert _draft().structure.title == "LEGAL OPINION"


def test_a_fabricated_citation_is_reported(monkeypatch):
    payload = dict(REPLY, sections=[
        {"heading": "THE POSITION",
         "paragraphs": [{"text": "X", "authorities": ["act:9999:sec-1"]}]},
    ])
    _stub(monkeypatch, payload)

    assert any("not retrieved" in f for f in _draft().failures)


def test_a_conversation_that_settled_nothing_never_reaches_the_model(monkeypatch):
    def boom(prompt, **kw):
        raise AssertionError("must not draft from a conversation with no law")

    monkeypatch.setattr(drafter, "generate", boom)
    result = draft("m", "c", "l", set())

    assert result.structure is None
    assert any("has not established any law" in f for f in result.failures)


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

    monkeypatch.setattr(drafter, "generate", boom)
    result = _draft()

    assert result.structure is None
    assert any("unreachable" in f for f in result.failures)


def test_one_model_call_per_document(monkeypatch):
    calls = []
    monkeypatch.setattr(
        drafter, "generate",
        lambda prompt, **kw: calls.append(1) or json.dumps(REPLY),
    )
    _draft()

    assert len(calls) == 1


def test_the_draft_budget_is_its_own_not_the_summary_budget(monkeypatch):
    seen = {}
    monkeypatch.setattr(
        drafter, "generate",
        lambda prompt, **kw: seen.update(kw) or json.dumps(REPLY),
    )
    _draft()

    from legal_ai.config import DEFAULT_CONFIG
    assert seen["max_output_tokens"] == DEFAULT_CONFIG.draft_model_max_tokens
