"""Deciding whether a message needs the corpus.

"Which of those binds me?" is a question about the answer already on screen.
Running the research fan-out for it costs thirty seconds and model budget to
re-find what the user is looking at.

The asymmetry is the whole design: answering from memory when the user
wanted fresh law is a wrong answer, while researching something we could
have answered from memory is only slow. So anything uncertain researches.
"""

import legal_ai.conversation.router as router_module
from legal_ai.conversation.router import Route, route_message
from legal_ai.conversation.rewriter import Turn

HISTORY = [
    Turn("user", "can a builder be made to refund for late possession"),
    Turn("assistant", "Yes, under RERA s.18 the allottee may withdraw and claim a refund."),
]


def _reply(monkeypatch, text):
    monkeypatch.setattr(router_module, "generate", lambda *a, **k: text)


def test_a_first_message_always_researches(monkeypatch):
    """Nothing to answer from, and no call worth spending to learn that."""
    calls = []
    monkeypatch.setattr(router_module, "generate", lambda *a, **k: calls.append(1) or "{}")
    assert route_message("can I get a refund", []) is Route.RESEARCH
    assert calls == []


def test_a_question_about_the_previous_answer_is_answered_from_it(monkeypatch):
    _reply(monkeypatch, '{"route": "ANSWER"}')
    assert route_message("which of those binds me", HISTORY) is Route.ANSWER


def test_a_new_legal_question_researches(monkeypatch):
    _reply(monkeypatch, '{"route": "RESEARCH"}')
    assert route_message("what about limitation periods", HISTORY) is Route.RESEARCH


def test_an_unreadable_reply_researches(monkeypatch):
    """Failing towards the slow path, never towards the confident one."""
    _reply(monkeypatch, "hard to say really")
    assert route_message("which of those binds me", HISTORY) is Route.RESEARCH


def test_an_unrecognised_route_researches(monkeypatch):
    _reply(monkeypatch, '{"route": "MAYBE"}')
    assert route_message("which of those binds me", HISTORY) is Route.RESEARCH


def test_an_error_researches(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("quota")

    monkeypatch.setattr(router_module, "generate", boom)
    assert route_message("which of those binds me", HISTORY) is Route.RESEARCH


def test_a_message_asking_for_current_law_always_researches(monkeypatch):
    """The model is not consulted for these. "Still good law" is exactly the
    question a stale answer gets wrong, and it must not be answerable from a
    reply given ten minutes ago."""
    calls = []
    monkeypatch.setattr(router_module, "generate", lambda *a, **k: calls.append(1) or '{"route": "ANSWER"}')
    for message in (
        "is that still good law",
        "has this been overruled since",
        "what is the current position",
        "any recent judgment on this",
    ):
        assert route_message(message, HISTORY) is Route.RESEARCH, message
    assert calls == []


def test_one_call_per_decision(monkeypatch):
    calls = []
    monkeypatch.setattr(
        router_module, "generate",
        lambda *a, **k: (calls.append(1), '{"route": "ANSWER"}')[1],
    )
    route_message("which of those binds me", HISTORY)
    assert len(calls) == 1
