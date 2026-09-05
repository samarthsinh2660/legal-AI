"""A draft is assembled from the thread it came out of.

The authorities in particular: a draft may cite what this conversation
established and nothing else, so they are read from the claims already
stored in the thread rather than retrieved afresh.
"""

from dataclasses import dataclass
from datetime import date

from api.drafts.source import (
    thread_authorities,
    thread_conversation,
)


@dataclass
class FakeMessage:
    role: str
    content: str
    answer: dict | None = None


def _answered(text, *evidence_ids):
    return FakeMessage(
        role="assistant",
        content=text,
        answer={"key_elements": [{"text": "a claim", "evidence_ids": list(evidence_ids)}]},
    )


def test_the_authorities_are_the_ones_the_thread_actually_used():
    messages = [
        FakeMessage(role="user", content="the cheque bounced, what now"),
        _answered("Section 138 applies.", "act:2189:sec-138", "act:2189:sec-139"),
        FakeMessage(role="user", content="how long to file"),
        _answered("One month under s.142.", "act:2189:sec-142"),
    ]

    assert thread_authorities(messages) == {
        "act:2189:sec-138", "act:2189:sec-139", "act:2189:sec-142",
    }


def test_a_thread_that_established_nothing_offers_no_authorities():
    """Then the drafter has nothing to cite, and validate refuses the
    draft rather than letting it invent one."""
    messages = [FakeMessage(role="user", content="hello")]

    assert thread_authorities(messages) == set()


def test_a_message_with_no_structured_answer_is_skipped():
    messages = [
        FakeMessage(role="assistant", content="plain reply", answer=None),
        _answered("cited", "act:2189:sec-138"),
    ]

    assert thread_authorities(messages) == {"act:2189:sec-138"}


def test_the_conversation_reads_as_questions_and_answers():
    messages = [
        FakeMessage(role="user", content="the cheque bounced"),
        FakeMessage(role="assistant", content="Section 138 applies."),
    ]
    rendered = thread_conversation(messages)

    assert "Q: the cheque bounced" in rendered
    assert "A: Section 138 applies." in rendered


def test_a_long_answer_is_cut_rather_than_pasted_whole():
    messages = [FakeMessage(role="assistant", content="word " * 4000)]

    assert len(thread_conversation(messages)) < 1200


def test_only_the_recent_turns_are_carried():
    messages = [FakeMessage(role="user", content=f"question {i}") for i in range(40)]
    rendered = thread_conversation(messages)

    assert "question 39" in rendered
    assert "question 0" not in rendered
