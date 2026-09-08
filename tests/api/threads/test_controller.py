"""Accepting a message.

The API's whole part in a turn: refuse what is not this user's, store the
question, filter the documents and queue the job. What the answer is, and
how it is produced, is `tests/worker/`.
"""

import pytest

from api.databases.postgres import connection
from api.runs import repository as runs
from api.threads import controller as thread_controller
from api.threads.repository import (
    create_thread,
    ensure_thread_schema,
    get_thread,
    list_messages,
)
from api.utils.errors import Failure, Ok

USER = "test-user-ctl"


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


def test_a_message_is_stored_and_queued():
    with connection() as conn:
        thread = create_thread(conn, USER)
        result = thread_controller.send_message(
            conn, USER, thread.thread_id, "can I get a refund"
        )
        stored = list_messages(conn, thread.thread_id, USER)
        run = runs.get(conn, result.value["run_id"], USER)

    assert isinstance(result, Ok)
    assert result.value["status"] == "queued"
    assert [message.content for message in stored] == ["can I get a refund"]
    assert run["kind"] == "research"


def test_the_job_carries_everything_the_worker_needs():
    """A worker reads the row and nothing else -- it may not be on this
    machine, let alone in this process.

    Read straight from the row rather than claimed: a real worker against
    the same database would take the job first, and this is a question
    about what `enqueue` wrote, not about who gets it.
    """
    with connection() as conn:
        thread = create_thread(conn, USER)
        result = thread_controller.send_message(
            conn, USER, thread.thread_id, "a question", verification_level="verified"
        )
        payload = conn.execute(
            "SELECT payload FROM runs WHERE run_id = %s", (result.value["run_id"],)
        ).fetchone()[0]

    assert payload["message"] == "a question"
    assert payload["verification_level"] == "verified"
    assert payload["message_id"] > 0


def test_another_users_thread_is_refused():
    with connection() as conn:
        thread = create_thread(conn, USER)
        result = thread_controller.send_message(
            conn, "someone-else", thread.thread_id, "hello"
        )
    assert isinstance(result, Failure)
    assert result.status == 404


def test_an_unknown_thread_is_refused():
    with connection() as conn:
        result = thread_controller.send_message(conn, USER, "no-such-id", "hello")
    assert isinstance(result, Failure) and result.status == 404


def test_the_first_message_titles_the_thread():
    """A sidebar of "New thread" is unusable."""
    with connection() as conn:
        thread = create_thread(conn, USER)
        thread_controller.send_message(
            conn, USER, thread.thread_id,
            "can a builder be made to refund for late possession",
        )
        titled = get_thread(conn, thread.thread_id, USER)
    assert titled.title != "New thread"
    assert "refund" in titled.title.lower()


def test_a_later_message_does_not_retitle():
    with connection() as conn:
        thread = create_thread(conn, USER)
        first = thread_controller.send_message(
            conn, USER, thread.thread_id, "first question here"
        )
        # The first run has to be out of the way; one thread runs one turn.
        # Closed directly rather than claimed, because a real worker against
        # this database may have claimed it already.
        runs.finish(conn, first.value["run_id"], {})
        thread_controller.send_message(conn, USER, thread.thread_id, "second question here")
        titled = get_thread(conn, thread.thread_id, USER)
    assert "first" in titled.title.lower()


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


def test_no_requested_documents_defaults_to_the_whole_case():
    from api.threads.controller import _permitted_documents
    from legal_ai.case.files import ensure_case_file_schema, store_case_file
    from legal_ai.case.store import create_case, ensure_case_schema

    with connection() as conn:
        ensure_case_schema(conn)
        ensure_case_file_schema(conn)
        conn.execute("DELETE FROM cases WHERE case_id LIKE 'test-perm-%'")
        conn.commit()
        create_case(conn, case_id="test-perm-default", title="Default")
        store_case_file(conn, "test-perm-default", "doc:notice", "notice.txt", "text")

        allowed = _permitted_documents(conn, "test-perm-default", None)
        conn.execute("DELETE FROM cases WHERE case_id LIKE 'test-perm-%'")
        conn.commit()

    assert allowed == ["doc:notice"]


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


def test_a_draft_in_flight_does_not_block_the_next_question():
    """The gate matched any kind, so preparing a document refused the next
    question with "This thread is still working on the last message" --
    which describes something else entirely. Drafting reads the thread; it
    does not write to it, so a question alongside one is fine."""
    from api.drafts import controller as drafts

    with connection() as conn:
        thread = create_thread(conn, USER)
        drafts.start_draft(conn, USER, thread.thread_id)
        conn.commit()

        assert isinstance(
            thread_controller.send_message(conn, USER, thread.thread_id, "a question"),
            Ok,
        )


def test_two_questions_at_once_are_still_refused():
    with connection() as conn:
        thread = create_thread(conn, USER)
        thread_controller.send_message(conn, USER, thread.thread_id, "first")
        conn.commit()
        second = thread_controller.send_message(conn, USER, thread.thread_id, "second")

    assert isinstance(second, Failure)
    assert second.code == "run_in_progress"
