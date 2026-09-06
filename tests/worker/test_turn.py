"""One turn of a thread.

Cross-domain: chat x thread x research.

The worker is where the phase's two findings meet. A follow-up is rewritten
before it reaches retrieval, because "what about Bombay" retrieves nothing
on its own. And a message about the answer already given is answered from it
rather than re-running a thirty-second fan-out.

Both fall back towards doing more work, never less: a broken rewriter sends
the user's own words, and an uncertain route researches.
"""

import pytest

from api.databases.postgres import connection
from api.runs import repository as runs
from api.threads.controller import send_message
from api.threads.repository import (
    add_message,
    create_thread,
    ensure_thread_schema,
    list_messages,
)
from legal_ai.conversation.router import Route
from worker import research as job

USER = "test-user-turn"


@pytest.fixture(autouse=True)
def _clean():
    with connection() as conn:
        ensure_thread_schema(conn)
        runs.ensure_run_schema(conn)
        conn.execute("DELETE FROM threads WHERE user_id LIKE 'test-user-%'")
        conn.commit()
    yield
    with connection() as conn:
        conn.execute("DELETE FROM threads WHERE user_id LIKE 'test-user-%'")
        conn.commit()


def _no_research(monkeypatch, state=None):
    """Stand in for the graph, and record what it was asked."""
    def fake(inputs):
        fake.seen = inputs
        yield "done", state or {"answer": "researched", "draft_answer": None}

    fake.seen = None
    monkeypatch.setattr(job, "stream_graph", fake)
    return fake


def _run(conn, thread_id: str, message: str) -> dict:
    """Send and immediately run the job, as a worker would."""
    send_message(conn, USER, thread_id, message)
    conn.commit()
    claimed = runs.claim(conn, ("research",))
    job.run(claimed)
    return claimed


def _reply(conn, run_id: str) -> dict:
    """The run's terminal event -- what the reader is handed."""
    events = runs.events_after(conn, run_id, 0)
    return events[-1]["payload"]


def test_a_first_message_researches_and_is_stored(monkeypatch):
    _no_research(monkeypatch)
    monkeypatch.setattr(job, "route_message", lambda *a, **k: Route.RESEARCH)
    with connection() as conn:
        thread = create_thread(conn, USER)
        claimed = _run(conn, thread.thread_id, "can I get a refund")
        assert _reply(conn, claimed["run_id"])["text"] == "researched"


def test_a_follow_up_reaches_retrieval_rewritten(monkeypatch):
    """The point of the phase: the graph must receive the standalone
    question, not "what about bombay"."""
    research = _no_research(monkeypatch)
    monkeypatch.setattr(job, "route_message", lambda *a, **k: Route.RESEARCH)
    monkeypatch.setattr(
        job, "rewrite_question",
        lambda q, history, **k: "Has the Bombay High Court applied RERA s.18?",
    )
    with connection() as conn:
        thread = create_thread(conn, USER)
        add_message(conn, thread.thread_id, "user", "refund for late possession?")
        add_message(conn, thread.thread_id, "assistant", "Yes, under RERA s.18.")
        _run(conn, thread.thread_id, "what about bombay")

    assert research.seen["question"] == "Has the Bombay High Court applied RERA s.18?"


def test_the_users_own_words_are_what_gets_stored(monkeypatch):
    """The rewrite is a retrieval device. Showing it back as what they typed
    would rewrite their own history at them."""
    _no_research(monkeypatch)
    monkeypatch.setattr(job, "route_message", lambda *a, **k: Route.RESEARCH)
    monkeypatch.setattr(job, "rewrite_question", lambda q, h, **k: "REWRITTEN")
    with connection() as conn:
        thread = create_thread(conn, USER)
        add_message(conn, thread.thread_id, "user", "earlier")
        _run(conn, thread.thread_id, "what about bombay")
        stored = [m.content for m in list_messages(conn, thread.thread_id, USER)]

    assert "what about bombay" in stored
    assert "REWRITTEN" not in stored


STORED_ANSWER = {
    "question": "can I get a refund for late possession",
    "lede": "Yes, under RERA s.18.",
    "key_elements": [
        {"text": "Mrs Sunita Patel is the allottee of flat B-1204",
         "evidence_ids": ["case-file:deed"]},
    ],
    "applicable_law": [],
    "key_judgments": [],
    "needs_verification": [],
    "partially_supported": [],
    "unchecked": ["the promoter registered the project"],
    "support_not_checked": False,
    "citations": ["case-file:deed"],
}


def test_a_message_about_the_last_answer_skips_research(monkeypatch):
    research = _no_research(monkeypatch)
    monkeypatch.setattr(job, "route_message", lambda *a, **k: Route.ANSWER)
    monkeypatch.setattr(job, "answer_from_thread", lambda *a, **k: None)
    with connection() as conn:
        thread = create_thread(conn, USER)
        add_message(conn, thread.thread_id, "assistant", "RERA s.18 applies.")
        _run(conn, thread.thread_id, "which of those binds me")

    assert research.seen is None, "research must not have run"


def test_an_answered_follow_up_is_not_the_previous_reply_replayed(monkeypatch):
    """The defect. A new, specific question routed ANSWER used to come back
    as the previous answer word for word, with nothing saying it was a
    repeat."""
    import legal_ai.conversation.recall as recall

    _no_research(monkeypatch)
    monkeypatch.setattr(job, "route_message", lambda *a, **k: Route.ANSWER)
    monkeypatch.setattr(
        recall, "generate",
        lambda *a, **k: '{"claims": [1], "lede": "Mrs Sunita Patel, flat B-1204."}',
    )
    previous = "Yes, under RERA s.18.\n\n- lots of earlier prose"
    with connection() as conn:
        thread = create_thread(conn, USER)
        add_message(conn, thread.thread_id, "user", "can I get a refund")
        add_message(conn, thread.thread_id, "assistant", previous, answer=STORED_ANSWER)
        claimed = _run(conn, thread.thread_id, "what is my client's name and which flat")
        reply = _reply(conn, claimed["run_id"])

    assert reply["text"] != previous
    assert "Sunita Patel" in reply["text"]
    assert reply["answer"]["question"] == "what is my client's name and which flat"
    assert [claim["text"] for claim in reply["answer"]["key_elements"]] == [
        "Mrs Sunita Patel is the allottee of flat B-1204"
    ]


def test_a_carried_claim_keeps_its_bucket_through_the_turn(monkeypatch):
    """Re-emitting an unchecked claim as a checked one would launder "nobody
    looked" into "we looked and it holds"."""
    import legal_ai.conversation.recall as recall

    _no_research(monkeypatch)
    monkeypatch.setattr(job, "route_message", lambda *a, **k: Route.ANSWER)
    monkeypatch.setattr(
        recall, "generate", lambda *a, **k: '{"claims": [2], "lede": "Registration."}'
    )
    with connection() as conn:
        thread = create_thread(conn, USER)
        add_message(conn, thread.thread_id, "user", "can I get a refund")
        add_message(conn, thread.thread_id, "assistant", "earlier", answer=STORED_ANSWER)
        claimed = _run(conn, thread.thread_id, "is the project registered")
        answer = _reply(conn, claimed["run_id"])["answer"]

    assert answer["key_elements"] == []
    assert answer["unchecked"] == ["the promoter registered the project"]


def test_a_thread_that_cannot_answer_says_so(monkeypatch):
    """"We could not answer from the thread" is a real outcome. It must not
    replay, and `answer` stays null so no client renders it as an answer."""
    research = _no_research(monkeypatch)
    monkeypatch.setattr(job, "route_message", lambda *a, **k: Route.ANSWER)
    monkeypatch.setattr(job, "answer_from_thread", lambda *a, **k: None)
    previous = "Yes, under RERA s.18."
    with connection() as conn:
        thread = create_thread(conn, USER)
        add_message(conn, thread.thread_id, "assistant", previous, answer=STORED_ANSWER)
        claimed = _run(conn, thread.thread_id, "what is the stamp duty in Karnataka")
        reply = _reply(conn, claimed["run_id"])

    assert reply["answer"] is None
    assert reply["text"] == job.COULD_NOT_ANSWER
    assert previous not in reply["text"]
    assert research.seen is None, "it must not silently research either"


def test_small_talk_is_answered_without_a_model(monkeypatch):
    """"thanks!" once cost 80s and came back with the law on gratuity."""
    research = _no_research(monkeypatch)
    with connection() as conn:
        thread = create_thread(conn, USER)
        claimed = _run(conn, thread.thread_id, "thanks!")
        stored = list_messages(conn, thread.thread_id, USER)

    assert research.seen is None
    assert [message.role for message in stored] == ["user", "assistant"]
    assert _reply(conn, claimed["run_id"])["route"] == "ANSWER"


def test_a_turn_in_a_case_leaves_its_findings_behind(monkeypatch):
    """The reason a case exists: the fourth question should not re-derive
    what the first three settled."""
    from legal_ai.case.store import create_case, ensure_case_schema, get_case

    answer = {
        "key_elements": [
            {"text": "a promoter must refund on demand", "evidence_ids": ["act:2158:sec-18"]}
        ]
    }
    _no_research(monkeypatch, {"answer": "text", "draft_answer": object()})
    monkeypatch.setattr(job, "route_message", lambda *a, **k: Route.RESEARCH)
    monkeypatch.setattr(job, "_as_dict", lambda draft: answer)

    with connection() as conn:
        ensure_case_schema(conn)
        conn.execute("DELETE FROM cases WHERE case_id = 'test-find-case'")
        conn.commit()
        create_case(conn, case_id="test-find-case", title="Patel v. Shah")
        thread = create_thread(conn, USER, case_id="test-find-case")
        _run(conn, thread.thread_id, "can I get a refund")
        case = get_case(conn, "test-find-case")
        conn.execute("DELETE FROM cases WHERE case_id = 'test-find-case'")
        conn.commit()

    assert [f.claim for f in case.findings] == ["a promoter must refund on demand"]


def test_an_unverified_claim_does_not_become_a_case_finding(monkeypatch):
    """A claim the checker rejected must not be laundered into the case file
    and then seeded into the next question as established fact."""
    from legal_ai.case.store import create_case, ensure_case_schema, get_case

    # needs_verification, not key_elements: evidence is against this one.
    answer = {"key_elements": [], "needs_verification": ["a promoter faces prison"]}
    _no_research(monkeypatch, {"answer": "text", "draft_answer": object()})
    monkeypatch.setattr(job, "route_message", lambda *a, **k: Route.RESEARCH)
    monkeypatch.setattr(job, "_as_dict", lambda draft: answer)

    with connection() as conn:
        ensure_case_schema(conn)
        conn.execute("DELETE FROM cases WHERE case_id = 'test-find-case2'")
        conn.commit()
        create_case(conn, case_id="test-find-case2", title="Patel v. Shah")
        thread = create_thread(conn, USER, case_id="test-find-case2")
        _run(conn, thread.thread_id, "a question")
        case = get_case(conn, "test-find-case2")
        conn.execute("DELETE FROM cases WHERE case_id = 'test-find-case2'")
        conn.commit()

    assert all("prison" not in f.claim for f in case.findings)


def test_an_answered_turn_leaves_no_new_case_findings(monkeypatch):
    """Nothing new was established, so nothing new goes in the case file."""
    import legal_ai.conversation.recall as recall
    from legal_ai.case.store import create_case, ensure_case_schema, get_case

    _no_research(monkeypatch)
    monkeypatch.setattr(job, "route_message", lambda *a, **k: Route.ANSWER)
    monkeypatch.setattr(recall, "generate", lambda *a, **k: '{"claims": [1], "lede": "x"}')
    with connection() as conn:
        ensure_case_schema(conn)
        conn.execute("DELETE FROM cases WHERE case_id = 'test-find-case3'")
        conn.commit()
        create_case(conn, case_id="test-find-case3", title="Patel v. Shah")
        thread = create_thread(conn, USER, case_id="test-find-case3")
        add_message(conn, thread.thread_id, "assistant", "earlier", answer=STORED_ANSWER)
        _run(conn, thread.thread_id, "and the flat number")
        case = get_case(conn, "test-find-case3")
        conn.execute("DELETE FROM cases WHERE case_id = 'test-find-case3'")
        conn.commit()

    assert case.findings == () or list(case.findings) == []


def test_a_thread_with_no_case_records_nothing(monkeypatch):
    """A standalone thread has nowhere to leave findings, and must not
    invent a matter to hold them."""
    _no_research(monkeypatch, {"answer": "text", "draft_answer": None})
    monkeypatch.setattr(job, "route_message", lambda *a, **k: Route.RESEARCH)
    with connection() as conn:
        thread = create_thread(conn, USER)
        claimed = _run(conn, thread.thread_id, "a question")
        run = runs.get(conn, claimed["run_id"], USER)

    assert run["status"] == "done"
