"""Do these courts actually disagree?

Three outcomes, not two. "The courts agree" and "we could not check" are
different facts, and collapsing them is the same defect Phase 6 fixed for
verification: a check that failed must not read as a check that passed.
Asserting a split that does not exist makes settled law look open; missing
one leaves the reader exactly where they started.
"""

import legal_ai.agents.conflict as conflict_agent
from legal_ai.agents.conflict import ConflictStatus, check_conflict
from legal_ai.retrieval.authority import Authority
from legal_ai.retrieval.conflict import CourtHolding


def h(doc_id: str, court: str) -> CourtHolding:
    return CourtHolding(doc_id, court, "the court held something", Authority(doc_id))


PAIR = [h("j1", "Delhi High Court"), h("j2", "Bombay High Court")]


def _reply(monkeypatch, text):
    monkeypatch.setattr(conflict_agent, "generate", lambda *a, **k: text)


def test_a_reported_conflict_is_returned(monkeypatch):
    _reply(monkeypatch, '{"status": "CONFLICT", "why": "opposite on limitation",'
                        ' "document_ids": ["j1", "j2"]}')
    finding = check_conflict(PAIR)
    assert finding.status is ConflictStatus.CONFLICT
    assert finding.document_ids == ("j1", "j2")


def test_agreement_is_returned_as_consistent(monkeypatch):
    _reply(monkeypatch, '{"status": "CONSISTENT", "why": "same rule applied"}')
    assert check_conflict(PAIR).status is ConflictStatus.CONSISTENT


def test_an_unreadable_reply_is_not_checked_not_consistent(monkeypatch):
    """The failure this guards: a broken reply rendering as 'courts agree',
    which is a claim about the law we never made."""
    _reply(monkeypatch, "the model was chatty and returned no JSON")
    finding = check_conflict(PAIR)
    assert finding.status is ConflictStatus.NOT_CHECKED
    assert finding.status is not ConflictStatus.CONSISTENT


def test_an_unrecognised_status_is_not_checked(monkeypatch):
    _reply(monkeypatch, '{"status": "MAYBE", "why": "unsure"}')
    assert check_conflict(PAIR).status is ConflictStatus.NOT_CHECKED


def test_fewer_than_two_courts_is_not_checked_without_a_call(monkeypatch):
    """One court is not a split, and must not spend a model call."""
    calls = []
    monkeypatch.setattr(conflict_agent, "generate",
                        lambda *a, **k: calls.append(1) or '{"status": "CONSISTENT"}')
    finding = check_conflict([h("only", "Delhi High Court")])
    assert finding.status is ConflictStatus.NOT_CHECKED
    assert calls == []


def test_no_holdings_at_all(monkeypatch):
    assert check_conflict([]).status is ConflictStatus.NOT_CHECKED


def test_ids_the_model_invented_are_dropped(monkeypatch):
    """A conflict must point at judgments the reader can open."""
    _reply(monkeypatch, '{"status": "CONFLICT", "why": "split",'
                        ' "document_ids": ["j1", "judgment:not-in-front-of-it"]}')
    assert check_conflict(PAIR).document_ids == ("j1",)


def test_one_call_per_check(monkeypatch):
    calls = []
    monkeypatch.setattr(conflict_agent, "generate",
                        lambda *a, **k: (calls.append(1), '{"status": "CONSISTENT"}')[1])
    check_conflict(PAIR)
    assert len(calls) == 1
