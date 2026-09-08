"""Stopping a run that nobody is waiting for.

Python cannot interrupt the blocking call a worker is inside, so a run
cannot be killed -- but it can be told not to start the next node. That is
the whole mechanism, and it is why cancellation could not exist while a
turn was an asyncio task in one process's memory.

What it buys is money: a reader who closes the tab currently pays for the
rest of the run.
"""

from __future__ import annotations

import pytest

from api.databases.postgres import connection
from api.runs import repository as runs
from api.threads.repository import create_thread, ensure_thread_schema

USER = "test-user-cancel"
OTHER = "test-user-cancel-other"


@pytest.fixture(autouse=True)
def _clean():
    with connection() as conn:
        ensure_thread_schema(conn)
        runs.ensure_run_schema(conn)
        conn.execute("DELETE FROM threads WHERE user_id LIKE 'test-user-cancel%'")
        conn.commit()
    yield
    with connection() as conn:
        conn.execute("DELETE FROM threads WHERE user_id LIKE 'test-user-cancel%'")
        conn.commit()


def _queued(conn):
    thread = create_thread(conn, USER)
    return runs.enqueue(conn, thread.thread_id, USER, "research", {})


def test_a_queued_run_can_be_cancelled_before_it_starts():
    with connection() as conn:
        run_id = _queued(conn)
        assert runs.cancel(conn, run_id, USER) is True
        assert runs.get(conn, run_id, USER)["status"] == "cancelled"


def test_a_cancelled_run_is_never_claimed():
    """The cheapest cancellation there is: it never costs a model call."""
    with connection() as conn:
        run_id = _queued(conn)
        runs.cancel(conn, run_id, USER)
        claimed = runs.claim(conn, ("research",))
        assert claimed is None or claimed["run_id"] != run_id


def test_a_running_run_can_be_cancelled_and_the_worker_is_told():
    """The worker learns of it through `beat`, which is the one round-trip
    it already makes at every node."""
    with connection() as conn:
        _queued(conn)
        job = runs.claim(conn, ("research",))

        assert runs.cancel(conn, job["run_id"], USER) is True
        assert runs.beat(conn, job["run_id"]) == "cancelled"


def test_a_run_still_going_is_not_reported_as_cancelled():
    with connection() as conn:
        _queued(conn)
        job = runs.claim(conn, ("research",))
        assert runs.beat(conn, job["run_id"]) == "running"


def test_a_finished_run_cannot_be_cancelled_after_the_fact():
    """The answer is stored and paid for. Marking it cancelled would throw
    away something the reader can still use."""
    with connection() as conn:
        _queued(conn)
        run_id = runs.claim(conn, ("research",))["run_id"]
        runs.finish(conn, run_id, {"text": "the answer"})

        assert runs.cancel(conn, run_id, USER) is False
        assert runs.get(conn, run_id, USER)["status"] == "done"


def test_another_user_cannot_cancel_a_run():
    with connection() as conn:
        run_id = _queued(conn)
        assert runs.cancel(conn, run_id, OTHER) is False
        assert runs.get(conn, run_id, USER)["status"] == "queued"


def test_cancelling_tells_whoever_is_watching():
    """A stream ends on a terminal event. Without one the reader's page sits
    on a run that has stopped."""
    with connection() as conn:
        run_id = _queued(conn)
        runs.cancel(conn, run_id, USER)
        events = runs.events_after(conn, run_id, 0)

    assert events[-1]["kind"] == "error"
    assert events[-1]["payload"]["code"] == "cancelled"


def test_a_cancelled_run_stops_being_the_threads_live_run():
    with connection() as conn:
        thread = create_thread(conn, USER)
        run_id = runs.enqueue(conn, thread.thread_id, USER, "research", {})
        runs.cancel(conn, run_id, USER)

        assert runs.live_for_thread(conn, thread.thread_id, USER) is None


def test_a_cancelled_run_frees_the_thread_for_the_next_question():
    """One run per thread is enforced against the live run, so a cancel
    that did not clear it would lock the thread out for good."""
    from api.threads.controller import send_message
    from api.utils.errors import Ok

    with connection() as conn:
        thread = create_thread(conn, USER)
        first = send_message(conn, USER, thread.thread_id, "first question")
        runs.cancel(conn, first.value["run_id"], USER)

        assert isinstance(send_message(conn, USER, thread.thread_id, "second"), Ok)
