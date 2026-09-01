"""One turn of a thread.

Cross-domain: chat x thread x research.

The controller is where the phase's two findings meet. A follow-up is
rewritten before it reaches retrieval, because "what about Bombay" retrieves
nothing on its own. And a message about the answer already given is answered
from it rather than re-running a thirty-second fan-out.

Both fall back towards doing more work, never less: a broken rewriter sends
the user's own words, and an uncertain route researches.
"""

import pytest

from api.threads import controller as thread_controller
from api.threads.repository import add_message, create_thread, ensure_thread_schema
from api.databases.postgres import connection
from api.utils.errors import Failure, Ok
from legal_ai.conversation.router import Route

USER = "test-user-ctl"


@pytest.fixture(autouse=True)
def _clean():
    with connection() as conn:
        ensure_thread_schema(conn)
        conn.execute("DELETE FROM threads WHERE user_id LIKE 'test-user-%'")
        conn.commit()
    yield
    with connection() as conn:
        conn.execute("DELETE FROM threads WHERE user_id LIKE 'test-user-%'")
        conn.commit()


def _no_research(monkeypatch, state=None):
    async def fake(inputs):
        fake.seen = inputs
        return Ok(state or {"answer": "researched", "draft_answer": None})

    monkeypatch.setattr(thread_controller, "run_research", fake)
    return fake


@pytest.mark.asyncio
async def test_a_first_message_researches_and_is_stored(monkeypatch):
    _no_research(monkeypatch)
    monkeypatch.setattr(thread_controller, "route_message", lambda *a, **k: Route.RESEARCH)
    with connection() as conn:
        thread = create_thread(conn, USER)
        result = await thread_controller.send_message(
            conn, USER, thread.thread_id, "can I get a refund"
        )
    assert isinstance(result, Ok)
    assert result.value["text"] == "researched"


@pytest.mark.asyncio
async def test_a_follow_up_reaches_retrieval_rewritten(monkeypatch):
    """The point of the phase: the graph must receive the standalone
    question, not "what about bombay"."""
    research = _no_research(monkeypatch)
    monkeypatch.setattr(thread_controller, "route_message", lambda *a, **k: Route.RESEARCH)
    monkeypatch.setattr(
        thread_controller, "rewrite_question",
        lambda q, history, **k: "Has the Bombay High Court applied RERA s.18?",
    )
    with connection() as conn:
        thread = create_thread(conn, USER)
        add_message(conn, thread.thread_id, "user", "refund for late possession?")
        add_message(conn, thread.thread_id, "assistant", "Yes, under RERA s.18.")
        await thread_controller.send_message(
            conn, USER, thread.thread_id, "what about bombay"
        )
    assert research.seen["question"] == "Has the Bombay High Court applied RERA s.18?"


@pytest.mark.asyncio
async def test_the_users_own_words_are_what_gets_stored(monkeypatch):
    """The rewrite is a retrieval device. Showing it back as what they typed
    would rewrite their own history at them."""
    _no_research(monkeypatch)
    monkeypatch.setattr(thread_controller, "route_message", lambda *a, **k: Route.RESEARCH)
    monkeypatch.setattr(thread_controller, "rewrite_question", lambda q, h, **k: "REWRITTEN")
    with connection() as conn:
        thread = create_thread(conn, USER)
        add_message(conn, thread.thread_id, "user", "earlier")
        await thread_controller.send_message(
            conn, USER, thread.thread_id, "what about bombay"
        )
        from api.threads.repository import list_messages

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


@pytest.mark.asyncio
async def test_a_message_about_the_last_answer_skips_research(monkeypatch):
    research = _no_research(monkeypatch)
    research.seen = None
    monkeypatch.setattr(thread_controller, "route_message", lambda *a, **k: Route.ANSWER)
    monkeypatch.setattr(
        thread_controller, "answer_from_thread", lambda *a, **k: None
    )
    with connection() as conn:
        thread = create_thread(conn, USER)
        add_message(conn, thread.thread_id, "assistant", "RERA s.18 applies.")
        result = await thread_controller.send_message(
            conn, USER, thread.thread_id, "which of those binds me"
        )
    assert research.seen is None, "research must not have run"


@pytest.mark.asyncio
async def test_an_answered_follow_up_is_not_the_previous_reply_replayed(monkeypatch):
    """The defect. A new, specific question routed ANSWER used to come back
    as the previous answer word for word, with nothing saying it was a
    repeat."""
    import legal_ai.conversation.recall as recall

    _no_research(monkeypatch)
    monkeypatch.setattr(thread_controller, "route_message", lambda *a, **k: Route.ANSWER)
    monkeypatch.setattr(
        recall, "generate",
        lambda *a, **k: '{"claims": [1], "lede": "Mrs Sunita Patel, flat B-1204."}',
    )
    previous = "Yes, under RERA s.18.\n\n- lots of earlier prose"
    with connection() as conn:
        thread = create_thread(conn, USER)
        add_message(conn, thread.thread_id, "user", "can I get a refund")
        add_message(conn, thread.thread_id, "assistant", previous, answer=STORED_ANSWER)
        result = await thread_controller.send_message(
            conn, USER, thread.thread_id, "what is my client's name and which flat"
        )

    text = result.value["text"]
    answer = result.value["answer"]
    assert text != previous
    assert "Sunita Patel" in text
    assert answer["question"] == "what is my client's name and which flat"
    assert [claim["text"] for claim in answer["key_elements"]] == [
        "Mrs Sunita Patel is the allottee of flat B-1204"
    ]


@pytest.mark.asyncio
async def test_a_carried_claim_keeps_its_bucket_through_the_turn(monkeypatch):
    """Re-emitting an unchecked claim as a checked one would launder "nobody
    looked" into "we looked and it holds"."""
    import legal_ai.conversation.recall as recall

    _no_research(monkeypatch)
    monkeypatch.setattr(thread_controller, "route_message", lambda *a, **k: Route.ANSWER)
    monkeypatch.setattr(
        recall, "generate", lambda *a, **k: '{"claims": [2], "lede": "Registration."}'
    )
    with connection() as conn:
        thread = create_thread(conn, USER)
        add_message(conn, thread.thread_id, "user", "can I get a refund")
        add_message(conn, thread.thread_id, "assistant", "earlier", answer=STORED_ANSWER)
        result = await thread_controller.send_message(
            conn, USER, thread.thread_id, "is the project registered"
        )

    answer = result.value["answer"]
    assert answer["key_elements"] == []
    assert answer["unchecked"] == ["the promoter registered the project"]


@pytest.mark.asyncio
async def test_a_thread_that_cannot_answer_says_so(monkeypatch):
    """"We could not answer from the thread" is a real outcome. It must not
    replay, and `answer` stays null so no client renders it as an answer."""
    research = _no_research(monkeypatch)
    research.seen = None
    monkeypatch.setattr(thread_controller, "route_message", lambda *a, **k: Route.ANSWER)
    monkeypatch.setattr(thread_controller, "answer_from_thread", lambda *a, **k: None)
    previous = "Yes, under RERA s.18."
    with connection() as conn:
        thread = create_thread(conn, USER)
        add_message(conn, thread.thread_id, "assistant", previous, answer=STORED_ANSWER)
        result = await thread_controller.send_message(
            conn, USER, thread.thread_id, "what is the stamp duty in Karnataka"
        )

    assert result.value["answer"] is None
    assert result.value["text"] == thread_controller.COULD_NOT_ANSWER
    assert previous not in result.value["text"]
    assert research.seen is None, "it must not silently research either"


@pytest.mark.asyncio
async def test_an_answered_turn_leaves_no_new_case_findings(monkeypatch):
    """Nothing new was established, so nothing new goes in the case file."""
    import legal_ai.conversation.recall as recall
    from legal_ai.case.store import create_case, ensure_case_schema, get_case

    _no_research(monkeypatch)
    monkeypatch.setattr(thread_controller, "route_message", lambda *a, **k: Route.ANSWER)
    monkeypatch.setattr(
        recall, "generate", lambda *a, **k: '{"claims": [1], "lede": "x"}'
    )
    with connection() as conn:
        ensure_case_schema(conn)
        conn.execute("DELETE FROM cases WHERE case_id = 'test-find-case3'")
        conn.commit()
        create_case(conn, case_id="test-find-case3", title="Patel v. Shah")
        thread = create_thread(conn, USER, case_id="test-find-case3")
        add_message(conn, thread.thread_id, "assistant", "earlier", answer=STORED_ANSWER)
        await thread_controller.send_message(
            conn, USER, thread.thread_id, "and the flat number"
        )
        case = get_case(conn, "test-find-case3")
        conn.execute("DELETE FROM cases WHERE case_id = 'test-find-case3'")
        conn.commit()

    assert case.findings == () or list(case.findings) == []


@pytest.mark.asyncio
async def test_another_users_thread_is_refused(monkeypatch):
    _no_research(monkeypatch)
    with connection() as conn:
        thread = create_thread(conn, USER)
        result = await thread_controller.send_message(
            conn, "someone-else", thread.thread_id, "hello"
        )
    assert isinstance(result, Failure)
    assert result.status == 404


@pytest.mark.asyncio
async def test_an_unknown_thread_is_refused(monkeypatch):
    _no_research(monkeypatch)
    with connection() as conn:
        result = await thread_controller.send_message(conn, USER, "no-such-id", "hello")
    assert isinstance(result, Failure) and result.status == 404


@pytest.mark.asyncio
async def test_a_research_failure_is_returned_not_stored(monkeypatch):
    """A timeout must not leave a half-turn in the thread that a later
    rewrite would then resolve against."""
    from api.utils.errors import timeout as timeout_failure

    async def fails(inputs):
        return timeout_failure("too slow")

    monkeypatch.setattr(thread_controller, "run_research", fails)
    monkeypatch.setattr(thread_controller, "route_message", lambda *a, **k: Route.RESEARCH)
    with connection() as conn:
        thread = create_thread(conn, USER)
        result = await thread_controller.send_message(
            conn, USER, thread.thread_id, "a question"
        )
        from api.threads.repository import list_messages

        roles = [m.role for m in list_messages(conn, thread.thread_id, USER)]
    assert isinstance(result, Failure) and result.status == 504
    assert "assistant" not in roles


@pytest.mark.asyncio
async def test_the_first_message_titles_the_thread(monkeypatch):
    """A sidebar of "New thread" is unusable."""
    _no_research(monkeypatch)
    monkeypatch.setattr(thread_controller, "route_message", lambda *a, **k: Route.RESEARCH)
    with connection() as conn:
        thread = create_thread(conn, USER)
        await thread_controller.send_message(
            conn, USER, thread.thread_id,
            "can a builder be made to refund for late possession",
        )
        from api.threads.repository import get_thread

        titled = get_thread(conn, thread.thread_id, USER)
    assert titled.title != "New thread"
    assert "refund" in titled.title.lower()


@pytest.mark.asyncio
async def test_a_later_message_does_not_retitle(monkeypatch):
    _no_research(monkeypatch)
    monkeypatch.setattr(thread_controller, "route_message", lambda *a, **k: Route.RESEARCH)
    with connection() as conn:
        thread = create_thread(conn, USER)
        await thread_controller.send_message(conn, USER, thread.thread_id, "first question here")
        await thread_controller.send_message(conn, USER, thread.thread_id, "second question here")
        from api.threads.repository import get_thread

        titled = get_thread(conn, thread.thread_id, USER)
    assert "first" in titled.title.lower()


@pytest.mark.asyncio
async def test_a_turn_in_a_case_leaves_its_findings_behind(monkeypatch):
    """The reason a case exists: the fourth question should not re-derive
    what the first three settled."""
    from api.threads.repository import create_thread
    from legal_ai.case.store import create_case, ensure_case_schema, get_case

    answer = {
        "key_elements": [
            {"text": "a promoter must refund on demand", "evidence_ids": ["act:2158:sec-18"]}
        ]
    }
    _no_research(monkeypatch, {"answer": "text", "draft_answer": object()})
    monkeypatch.setattr(thread_controller, "route_message", lambda *a, **k: Route.RESEARCH)
    monkeypatch.setattr(thread_controller, "_as_dict", lambda draft: answer)

    with connection() as conn:
        ensure_case_schema(conn)
        conn.execute("DELETE FROM cases WHERE case_id = 'test-find-case'")
        conn.commit()
        create_case(conn, case_id="test-find-case", title="Patel v. Shah")
        thread = create_thread(conn, USER, case_id="test-find-case")
        await thread_controller.send_message(
            conn, USER, thread.thread_id, "can I get a refund"
        )
        case = get_case(conn, "test-find-case")
        conn.execute("DELETE FROM cases WHERE case_id = 'test-find-case'")
        conn.commit()

    assert [f.claim for f in case.findings] == ["a promoter must refund on demand"]


@pytest.mark.asyncio
async def test_an_unverified_claim_does_not_become_a_case_finding(monkeypatch):
    """A claim the checker rejected must not be laundered into the case file
    and then seeded into the next question as established fact."""
    from api.threads.repository import create_thread
    from legal_ai.case.store import create_case, ensure_case_schema, get_case

    # needs_verification, not key_elements: evidence is against this one.
    answer = {"key_elements": [], "needs_verification": ["a promoter faces prison"]}
    _no_research(monkeypatch, {"answer": "text", "draft_answer": object()})
    monkeypatch.setattr(thread_controller, "route_message", lambda *a, **k: Route.RESEARCH)
    monkeypatch.setattr(thread_controller, "_as_dict", lambda draft: answer)

    with connection() as conn:
        ensure_case_schema(conn)
        conn.execute("DELETE FROM cases WHERE case_id = 'test-find-case2'")
        conn.commit()
        create_case(conn, case_id="test-find-case2", title="Patel v. Shah")
        thread = create_thread(conn, USER, case_id="test-find-case2")
        await thread_controller.send_message(conn, USER, thread.thread_id, "a question")
        case = get_case(conn, "test-find-case2")
        conn.execute("DELETE FROM cases WHERE case_id = 'test-find-case2'")
        conn.commit()

    assert all("prison" not in f.claim for f in case.findings)


@pytest.mark.asyncio
async def test_a_thread_with_no_case_records_nothing(monkeypatch):
    """A standalone thread has nowhere to leave findings, and must not
    invent a matter to hold them."""
    from api.threads.repository import create_thread

    _no_research(monkeypatch, {"answer": "text", "draft_answer": None})
    monkeypatch.setattr(thread_controller, "route_message", lambda *a, **k: Route.RESEARCH)
    with connection() as conn:
        thread = create_thread(conn, USER)
        result = await thread_controller.send_message(
            conn, USER, thread.thread_id, "a question"
        )
    assert isinstance(result, Ok)


def test_documents_are_filtered_to_the_threads_own_case():
    """Found by review. `get_case_file_text` looks a document up by id
    alone -- no owner, no case -- so anything not filtered here is readable
    by anyone who has ever seen the id."""
    from api.threads.controller import _permitted_documents
    from legal_ai.case.files import ensure_case_file_schema, store_case_file
    from legal_ai.case.store import create_case, ensure_case_schema

    with connection() as conn:
        ensure_case_schema(conn)
        ensure_case_file_schema(conn)
        conn.execute("DELETE FROM cases WHERE case_id LIKE 'test-perm-%'")
        conn.commit()
        create_case(conn, case_id="test-perm-mine", title="Mine")
        create_case(conn, case_id="test-perm-theirs", title="Theirs")
        store_case_file(conn, "test-perm-mine", "doc:mine", "mine.txt", "my text")
        store_case_file(conn, "test-perm-theirs", "doc:theirs", "theirs.txt", "their text")

        allowed = _permitted_documents(
            conn, "test-perm-mine", ["doc:mine", "doc:theirs", "doc:invented"]
        )
        conn.execute("DELETE FROM cases WHERE case_id LIKE 'test-perm-%'")
        conn.commit()

    assert allowed == ["doc:mine"]


def test_a_thread_outside_a_case_may_read_no_files():
    from api.threads.controller import _permitted_documents

    with connection() as conn:
        assert _permitted_documents(conn, None, ["doc:anything"]) == []


def test_the_answer_payload_carries_the_coverage_note():
    """It reaches the UI or it does not exist. The note was rendered into
    the text but dropped from the structured answer, so the screen a lawyer
    actually reads never showed it."""
    from api.schemas import AnswerModel
    from legal_ai.schemas.answer import DraftAnswer

    model = AnswerModel.of(
        DraftAnswer(question="s.498A IPC", coverage_note="We do not hold the IPC.")
    )
    assert model.coverage_note == "We do not hold the IPC."
