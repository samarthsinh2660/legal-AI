"""A run is a row, and its progress is rows under it.

The point of both is a reconnect: a browser that drops mid-run sends the
last event id it saw, and gets the rest replayed rather than a spinner and
a guess.
"""

from __future__ import annotations

import pytest

from api.databases.postgres import connection
from api.runs import repository as runs
from api.threads.repository import create_thread, ensure_thread_schema

USER = "test-user-run"
OTHER = "test-user-run-other"


@pytest.fixture(autouse=True)
def _clean():
    with connection() as conn:
        ensure_thread_schema(conn)
        runs.ensure_run_schema(conn)
        conn.execute("DELETE FROM threads WHERE user_id LIKE 'test-user-run%'")
        conn.commit()
    yield
    with connection() as conn:
        conn.execute("DELETE FROM threads WHERE user_id LIKE 'test-user-run%'")
        conn.commit()


def test_a_run_is_visible_the_moment_it_is_queued():
    """Written before any worker sees it, so a reader reloading a second
    later finds a run in flight rather than a thread that looks abandoned."""
    with connection() as conn:
        thread = create_thread(conn, USER)
        run_id = runs.enqueue(conn, thread.thread_id, USER, "research", {})

        assert runs.get(conn, run_id, USER)["status"] == "queued"
        assert runs.live_for_thread(conn, thread.thread_id, USER)["run_id"] == run_id


def test_events_carry_a_dense_sequence_per_run():
    """The seq is what Last-Event-ID resumes against, so it must be
    per-run and gapless."""
    with connection() as conn:
        thread = create_thread(conn, USER)
        one = runs.enqueue(conn, thread.thread_id, USER, "research", {})
        two = runs.enqueue(conn, thread.thread_id, USER, "research", {})

        seqs_one = [runs.step(conn, one, f"n{i}", f"L{i}") for i in range(3)]
        seqs_two = [runs.step(conn, two, f"n{i}", f"L{i}") for i in range(2)]

    assert seqs_one == [1, 2, 3]
    assert seqs_two == [1, 2]


def test_a_reconnect_replays_only_what_was_missed():
    with connection() as conn:
        thread = create_thread(conn, USER)
        run_id = runs.enqueue(conn, thread.thread_id, USER, "research", {})
        for i in range(4):
            runs.step(conn, run_id, f"node{i}", f"Step {i}")

        missed = runs.events_after(conn, run_id, 2)

    assert [e["seq"] for e in missed] == [3, 4]
    assert missed[0]["payload"]["label"] == "Step 2"


def test_a_reconnect_that_saw_nothing_gets_the_whole_run():
    with connection() as conn:
        thread = create_thread(conn, USER)
        run_id = runs.enqueue(conn, thread.thread_id, USER, "research", {})
        runs.step(conn, run_id, "research", "Searching")

        assert len(runs.events_after(conn, run_id, 0)) == 1


def test_the_current_step_is_readable_without_walking_the_events():
    """What a reopened thread shows before its stream has said anything."""
    with connection() as conn:
        thread = create_thread(conn, USER)
        run_id = runs.enqueue(conn, thread.thread_id, USER, "research", {})
        runs.step(conn, run_id, "analyst", "Drafting the analysis")

        assert runs.get(conn, run_id, USER)["current_step"] == "analyst"


def test_a_finished_run_stops_being_live_and_keeps_its_answer():
    with connection() as conn:
        thread = create_thread(conn, USER)
        run_id = runs.enqueue(conn, thread.thread_id, USER, "research", {})
        runs.finish(conn, run_id, {"text": "the answer"})

        assert runs.get(conn, run_id, USER)["status"] == "done"
        assert runs.live_for_thread(conn, thread.thread_id, USER) is None
        assert runs.events_after(conn, run_id, 0)[-1]["payload"]["text"] == "the answer"


def test_a_failed_run_keeps_its_row_and_its_reason():
    """A run that vanishes is indistinguishable from one still going."""
    with connection() as conn:
        thread = create_thread(conn, USER)
        run_id = runs.enqueue(conn, thread.thread_id, USER, "research", {})
        runs.fail(conn, run_id, "timeout", "Research did not finish in time.")

        run = runs.get(conn, run_id, USER)
        last = runs.events_after(conn, run_id, 0)[-1]

    assert run["status"] == "failed"
    assert "did not finish" in run["error"]
    assert last["kind"] == "error" and last["payload"]["code"] == "timeout"


def test_another_users_run_is_invisible():
    with connection() as conn:
        thread = create_thread(conn, USER)
        run_id = runs.enqueue(conn, thread.thread_id, USER, "research", {})

        assert runs.get(conn, run_id, OTHER) is None
        assert runs.live_for_thread(conn, thread.thread_id, OTHER) is None


def test_deleting_a_thread_takes_its_runs_and_events_with_it():
    with connection() as conn:
        thread = create_thread(conn, USER)
        run_id = runs.enqueue(conn, thread.thread_id, USER, "research", {})
        runs.step(conn, run_id, "research", "Searching")
        conn.execute("DELETE FROM threads WHERE thread_id = %s", (thread.thread_id,))
        conn.commit()

        assert runs.get(conn, run_id, USER) is None
        assert runs.events_after(conn, run_id, 0) == []


# --- the table as a queue --------------------------------------------------


def test_claiming_takes_the_oldest_job_and_marks_it_running():
    with connection() as conn:
        thread = create_thread(conn, USER)
        first = runs.enqueue(conn, thread.thread_id, USER, "research", {"n": 1})
        runs.enqueue(conn, thread.thread_id, USER, "research", {"n": 2})

        job = runs.claim(conn, ("research",))

    assert job["run_id"] == first
    assert job["payload"] == {"n": 1}


def test_a_job_is_claimed_once_and_only_once():
    """`FOR UPDATE SKIP LOCKED` is the whole of the guarantee: without it two
    workers answer the same question and the user pays twice."""
    with connection() as conn:
        thread = create_thread(conn, USER)
        runs.enqueue(conn, thread.thread_id, USER, "research", {})

        first = runs.claim(conn, ("research",))
        second = runs.claim(conn, ("research",))

    assert first is not None
    assert second is None


def test_a_worker_claims_only_the_kinds_it_serves():
    with connection() as conn:
        thread = create_thread(conn, USER)
        runs.enqueue(conn, thread.thread_id, USER, "draft", {})

        assert runs.claim(conn, ("research",)) is None
        assert runs.claim(conn, ("draft",))["kind"] == "draft"


def test_a_claimed_job_carries_everything_the_worker_needs():
    """A worker reads the row and nothing else -- it may be on another
    machine, with no access to the request that created it."""
    with connection() as conn:
        thread = create_thread(conn, USER)
        runs.enqueue(
            conn, thread.thread_id, USER, "research",
            {"message": "what is section 138", "verification_level": "quick"},
        )

        job = runs.claim(conn, ("research",))

    assert job["thread_id"] == thread.thread_id
    assert job["user_id"] == USER
    assert job["payload"]["message"] == "what is section 138"


def test_an_empty_queue_hands_back_nothing_rather_than_waiting():
    with connection() as conn:
        assert runs.claim(conn, ("research", "draft")) is None
