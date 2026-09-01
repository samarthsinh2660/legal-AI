"""Turning a follow-up into a question retrieval can answer.

"What about Bombay?" retrieves nothing. Over 60% of follow-ups carry an
unresolved reference like that, and the fix every conversational-RAG paper
lands on is the same: rewrite against the recent turns first.

The rule that matters most here is failing open. A rewriter that errors must
give back the user's own words, because degrading to today's behaviour is
recoverable and returning nothing is not.
"""

import legal_ai.conversation.rewriter as rewriter_module
from legal_ai.conversation.rewriter import Turn, rewrite_question


def _reply(monkeypatch, text):
    monkeypatch.setattr(rewriter_module, "generate", lambda *a, **k: text)


HISTORY = [
    Turn("user", "can a builder be made to refund for late possession"),
    Turn("assistant", "Yes, under RERA s.18 the allottee may withdraw and claim a refund."),
]


def test_a_follow_up_is_expanded_into_a_standalone_question(monkeypatch):
    _reply(monkeypatch, '{"question": "Has the Bombay High Court applied RERA s.18 to late possession refunds?"}')
    out = rewrite_question("what about bombay", HISTORY)
    assert "Bombay" in out and "s.18" in out


def test_a_first_message_is_not_rewritten(monkeypatch):
    """Nothing to resolve against, and a model call would be spent turning a
    complete question into a different one."""
    calls = []
    monkeypatch.setattr(rewriter_module, "generate", lambda *a, **k: calls.append(1) or "{}")
    assert rewrite_question("can I get a refund", []) == "can I get a refund"
    assert calls == []


def test_an_unreadable_reply_falls_back_to_the_user_words(monkeypatch):
    _reply(monkeypatch, "I think you meant something about Bombay?")
    assert rewrite_question("what about bombay", HISTORY) == "what about bombay"


def test_an_error_falls_back_to_the_user_words(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("quota")

    monkeypatch.setattr(rewriter_module, "generate", boom)
    assert rewrite_question("what about bombay", HISTORY) == "what about bombay"


def test_an_empty_rewrite_falls_back(monkeypatch):
    """A blank standalone question would retrieve the whole corpus."""
    _reply(monkeypatch, '{"question": "   "}')
    assert rewrite_question("what about bombay", HISTORY) == "what about bombay"


def test_only_recent_turns_are_sent(monkeypatch):
    """Bounded on purpose: the rewriter needs the referent, not the
    transcript, and a long history buries it."""
    seen = {}
    monkeypatch.setattr(
        rewriter_module, "generate",
        lambda prompt, **k: seen.update(prompt=prompt) or '{"question": "x"}',
    )
    long_history = [Turn("user", f"turn {n}") for n in range(40)]
    rewrite_question("and then", long_history)
    assert "turn 39" in seen["prompt"]
    assert "turn 0" not in seen["prompt"]


def test_the_users_own_words_are_always_in_the_prompt(monkeypatch):
    seen = {}
    monkeypatch.setattr(
        rewriter_module, "generate",
        lambda prompt, **k: seen.update(prompt=prompt) or '{"question": "x"}',
    )
    rewrite_question("what about bombay", HISTORY)
    assert "what about bombay" in seen["prompt"]


def test_a_rewrite_that_is_absurdly_long_is_refused(monkeypatch):
    """A model that returns an essay instead of a question would push the
    real query out of the retrieval budget."""
    _reply(monkeypatch, '{"question": "' + "x" * 5000 + '"}')
    assert rewrite_question("what about bombay", HISTORY) == "what about bombay"


def test_history_is_labelled_by_speaker(monkeypatch):
    """Without roles the model cannot tell what it said from what was asked,
    and resolves the reference against the wrong turn."""
    seen = {}
    monkeypatch.setattr(
        rewriter_module, "generate",
        lambda prompt, **k: seen.update(prompt=prompt) or '{"question": "x"}',
    )
    rewrite_question("what about bombay", HISTORY)
    assert "user" in seen["prompt"].lower() and "assistant" in seen["prompt"].lower()


def test_one_call_per_rewrite(monkeypatch):
    calls = []
    monkeypatch.setattr(
        rewriter_module, "generate",
        lambda *a, **k: (calls.append(1), '{"question": "x"}')[1],
    )
    rewrite_question("what about bombay", HISTORY)
    assert len(calls) == 1
