"""Composing a follow-up's answer out of what the thread already established.

The defect this pins: a new, specific question routed ANSWER used to get the
previous reply word for word -- same lede, same claims, nothing about what
was asked. To a reader that is a broken product, and nothing on screen said
it was a repeat.

The rule that matters more than the composition is the one about buckets. A
claim carried into a new answer keeps the bucket it was in. Re-emitting an
unchecked claim as a checked one would launder "nobody looked" into "we
looked and it holds" -- the exact silent degradation the four slots exist to
prevent.
"""

import legal_ai.conversation.recall as recall_module
from legal_ai.conversation.recall import answer_from_thread

# Two stored answers from earlier in the thread. The second is the one the
# verbatim replay used to return.
STORED = [
    {
        "question": "can I get a refund for late possession",
        "lede": "Yes, under RERA s.18.",
        "key_elements": [
            {
                "text": "Mrs Sunita Patel is the allottee of flat B-1204",
                "evidence_ids": ["case-file:deed"],
            },
            {
                "text": "she has paid Rs 62,40,000 of the consideration",
                "evidence_ids": ["case-file:receipts"],
            },
        ],
        "applicable_law": [],
        "key_judgments": [],
        "needs_verification": [],
        "partially_supported": [],
        "unchecked": ["the promoter registered the project"],
        "support_not_checked": False,
        "citations": ["case-file:deed", "case-file:receipts"],
    },
    {
        "question": "what interest is payable",
        "lede": "Interest runs at SBI MCLR plus two per cent.",
        "key_elements": [
            {"text": "interest runs from the promised date",
             "evidence_ids": ["act:2158:sec-18"]},
        ],
        "applicable_law": ["act:2158:sec-18"],
        "key_judgments": [],
        "needs_verification": [],
        "partially_supported": [],
        "unchecked": [],
        "support_not_checked": False,
        "citations": ["act:2158:sec-18"],
    },
]

QUESTION = "what is my client's name, which flat, and how much has she paid?"


def _model(monkeypatch, reply):
    calls = []

    def fake(prompt, *a, **k):
        calls.append(prompt)
        return reply

    monkeypatch.setattr(recall_module, "generate", fake)
    return calls


def test_a_new_question_gets_a_new_answer_not_the_previous_one(monkeypatch):
    """The defect. Selecting claims 1 and 2 must produce an answer about
    them, with the previous lede nowhere in it."""
    _model(monkeypatch, '{"claims": [1, 2], "lede": "Mrs Sunita Patel, flat '
                        'B-1204, Rs 62,40,000 paid."}')
    answer = answer_from_thread(QUESTION, STORED)

    assert answer is not None
    assert answer.question == QUESTION
    assert "Sunita Patel" in answer.lede
    assert answer.lede != STORED[-1]["lede"]
    assert [claim.text for claim in answer.key_elements] == [
        "Mrs Sunita Patel is the allottee of flat B-1204",
        "she has paid Rs 62,40,000 of the consideration",
    ]


def test_a_carried_claim_keeps_its_bucket(monkeypatch):
    """Claim 3 is `unchecked`. Selecting it must not promote it."""
    _model(monkeypatch, '{"claims": [3], "lede": "The project registration."}')
    answer = answer_from_thread(QUESTION, STORED)

    assert answer.key_elements == ()
    assert answer.unchecked == ("the promoter registered the project",)


def test_the_weakest_bucket_wins_when_a_claim_was_stored_twice(monkeypatch):
    """The same text checked in one turn and unchecked in another is
    reported unchecked. Never the reassuring one."""
    both = [
        {"key_elements": [{"text": "the project is registered",
                           "evidence_ids": ["act:2158:sec-3"]}]},
        {"unchecked": ["the project is registered"]},
    ]
    _model(monkeypatch, '{"claims": [1], "lede": "x"}')
    answer = answer_from_thread(QUESTION, both)

    assert answer.key_elements == ()
    assert answer.unchecked == ("the project is registered",)


def test_the_model_cannot_introduce_an_evidence_id(monkeypatch):
    """Every id in the composed answer came from a stored claim. The model
    picks numbers; it never gets to write an identifier."""
    _model(monkeypatch, '{"claims": [1, 2, 3], "lede": "x", '
                        '"evidence_ids": ["act:9999:sec-1"]}')
    answer = answer_from_thread(QUESTION, STORED)

    stored_ids = {"case-file:deed", "case-file:receipts", "act:2158:sec-18"}
    used = {i for claim in answer.key_elements for i in claim.evidence_ids}
    assert used <= stored_ids
    assert set(answer.citations) <= stored_ids


def test_an_out_of_range_selection_is_dropped(monkeypatch):
    _model(monkeypatch, '{"claims": [1, 99, 0, -2, "x"], "lede": "x"}')
    answer = answer_from_thread(QUESTION, STORED)

    assert [claim.text for claim in answer.key_elements] == [
        "Mrs Sunita Patel is the allottee of flat B-1204"
    ]


def test_a_thread_holding_no_claims_costs_no_model_call(monkeypatch):
    """Deterministic before model. There is nothing to compose from, and a
    call cannot discover that."""
    calls = _model(monkeypatch, '{"claims": [1], "lede": "x"}')
    assert answer_from_thread(QUESTION, []) is None
    assert answer_from_thread(QUESTION, [{"key_elements": []}]) is None
    assert calls == []


def test_nothing_relevant_is_not_an_answer(monkeypatch):
    """"We could not answer from the thread" is a real outcome. It must not
    fall back to replaying, and must not render like an answer."""
    _model(monkeypatch, '{"claims": [], "lede": "I cannot tell from this."}')
    assert answer_from_thread(QUESTION, STORED) is None


def test_an_unreadable_reply_is_not_an_answer(monkeypatch):
    _model(monkeypatch, "sorry, hard to say")
    assert answer_from_thread(QUESTION, STORED) is None


def test_a_model_error_is_not_an_answer(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("quota")

    monkeypatch.setattr(recall_module, "generate", boom)
    assert answer_from_thread(QUESTION, STORED) is None


def test_quick_mode_carries_forward(monkeypatch):
    """A claim drawn from an answer whose support was never checked keeps
    that caveat. Dropping it would upgrade the claim by re-emitting it."""
    quick = [dict(STORED[0], support_not_checked=True)]
    _model(monkeypatch, '{"claims": [1], "lede": "x"}')
    assert answer_from_thread(QUESTION, quick).support_not_checked is True


def test_the_law_a_carried_claim_rests_on_is_carried_with_it(monkeypatch):
    """The stored answer already classified its ids. Re-deriving them here
    without the evidence in hand would be guesswork."""
    _model(monkeypatch, '{"claims": [4], "lede": "x"}')
    answer = answer_from_thread(QUESTION, STORED)

    assert answer.applicable_law == ("act:2158:sec-18",)
