"""Runs that stop breathing.

SIGTERM is already handled: the worker drains and the answer is stored. The
hole this closes is the unplanned death -- `kill -9`, an OOM, a lost
machine. The row says `running`, nothing is working on it, and a reader
waits on an answer that is never coming. That is indistinguishable from
slow, forever, which is the one failure this system is built not to have.

A heartbeat makes the difference visible: a worker that is alive advances
it, and a row whose heartbeat has stopped is a row nobody owns.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from api.databases.postgres import connection
from api.runs import repository as runs
from api.threads.repository import create_thread, ensure_thread_schema

USER = "test-user-reap"


@pytest.fixture(autouse=True)
def _clean():
    with connection() as conn:
        ensure_thread_schema(conn)
        runs.ensure_run_schema(conn)
        conn.execute("DELETE FROM threads WHERE user_id LIKE 'test-user-reap%'")
        conn.commit()
    yield
    with connection() as conn:
        conn.execute("DELETE FROM threads WHERE user_id LIKE 'test-user-reap%'")
        conn.commit()


def _claimed(conn, payload=None):
    """A run in the state a worker leaves it in: claimed and beating."""
    thread = create_thread(conn, USER)
    runs.enqueue(conn, thread.thread_id, USER, "research", payload or {})
    return runs.claim(conn, ("research",))


def _stop_beating(conn, run_id, ago_seconds):
    conn.execute(
        "UPDATE runs SET heartbeat_at = now() - %s::interval WHERE run_id = %s",
        (timedelta(seconds=ago_seconds), run_id),
    )
    conn.commit()


# --- the heartbeat ---------------------------------------------------------


def test_claiming_a_run_starts_its_heartbeat():
    with connection() as conn:
        job = _claimed(conn)
        assert runs.get(conn, job["run_id"], USER)["heartbeat_at"] is not None


def test_a_beat_moves_it_forward():
    with connection() as conn:
        job = _claimed(conn)
        _stop_beating(conn, job["run_id"], 600)
        before = runs.get(conn, job["run_id"], USER)["heartbeat_at"]

        runs.beat(conn, job["run_id"])

        assert runs.get(conn, job["run_id"], USER)["heartbeat_at"] > before


def test_a_queued_run_has_no_heartbeat_to_stop():
    """Nothing is working on it, so nothing should look like a death."""
    with connection() as conn:
        thread = create_thread(conn, USER)
        run_id = runs.enqueue(conn, thread.thread_id, USER, "research", {})
        assert runs.get(conn, run_id, USER)["heartbeat_at"] is None


# --- the sweep -------------------------------------------------------------


def test_a_run_still_beating_is_left_alone():
    with connection() as conn:
        job = _claimed(conn)
        assert runs.reap(conn, stale_after=60) == []
        assert runs.get(conn, job["run_id"], USER)["status"] == "running"


def test_a_run_that_stopped_beating_is_requeued_for_another_worker():
    with connection() as conn:
        job = _claimed(conn, {"message": "what is section 138"})
        _stop_beating(conn, job["run_id"], 600)

        assert runs.reap(conn, stale_after=60) == [job["run_id"]]

        run = runs.get(conn, job["run_id"], USER)
        assert run["status"] == "queued"
        # And it keeps everything a worker needs to run it again.
        assert runs.claim(conn, ("research",))["payload"]["message"] == "what is section 138"


def test_a_run_that_keeps_dying_is_failed_rather_than_requeued_forever():
    """A job that kills its worker would otherwise kill every worker in
    turn. Three attempts, then it is somebody's bug, not a blip."""
    with connection() as conn:
        job = _claimed(conn)
        for _ in range(runs.MAX_ATTEMPTS):
            _stop_beating(conn, job["run_id"], 600)
            runs.reap(conn, stale_after=60)
            runs.claim(conn, ("research",))

        _stop_beating(conn, job["run_id"], 600)
        runs.reap(conn, stale_after=60)

        run = runs.get(conn, job["run_id"], USER)
        assert run["status"] == "failed"
        assert "attempt" in (run["error"] or "").lower()


def test_a_failed_run_says_so_to_whoever_is_watching():
    """The reader is on a stream. A row that goes quiet is what this exists
    to prevent, so the terminal event has to be written too."""
    with connection() as conn:
        job = _claimed(conn)
        for _ in range(runs.MAX_ATTEMPTS + 1):
            _stop_beating(conn, job["run_id"], 600)
            runs.reap(conn, stale_after=60)
            runs.claim(conn, ("research",))

        events = runs.events_after(conn, job["run_id"], 0)

    assert events[-1]["kind"] == "error"


def test_a_finished_run_is_never_reaped():
    with connection() as conn:
        job = _claimed(conn)
        runs.finish(conn, job["run_id"], {"text": "the answer"})
        _stop_beating(conn, job["run_id"], 6000)

        assert runs.reap(conn, stale_after=60) == []
        assert runs.get(conn, job["run_id"], USER)["status"] == "done"


def test_a_requeued_run_wakes_a_worker_that_serves_its_own_kind():
    """The notification carries the row's kind. Hardcoding "research" woke
    the wrong workers for a requeued draft, and left the right ones asleep
    until their next sweep."""
    with connection() as conn:
        thread = create_thread(conn, USER)
        runs.enqueue(conn, thread.thread_id, USER, "draft", {})
        job = runs.claim(conn, ("draft",))
        _stop_beating(conn, job["run_id"], 600)

        conn.execute(f"LISTEN {runs.QUEUED_CHANNEL}")
        conn.commit()
        runs.reap(conn, stale_after=60)

        woken = [n.payload for n in conn.notifies(timeout=5, stop_after=1)]

    assert woken == ["draft"]


# --- one round trip, not three ---------------------------------------------


def test_beating_reports_what_it_found():
    """The worker asks three questions at every node -- is the run gone,
    was it cancelled, and here is my heartbeat. They are one row, so they
    should be one query: seven nodes were costing twenty-one."""
    with connection() as conn:
        job = _claimed(conn)
        _stop_beating(conn, job["run_id"], 600)
        before = runs.get(conn, job["run_id"], USER)["heartbeat_at"]

        assert runs.beat(conn, job["run_id"]) == "running"
        assert runs.get(conn, job["run_id"], USER)["heartbeat_at"] > before


def test_beating_a_deleted_run_reports_that_it_is_gone():
    with connection() as conn:
        job = _claimed(conn)
        conn.execute("DELETE FROM threads WHERE user_id = %s", (USER,))
        conn.commit()

        assert runs.beat(conn, job["run_id"]) is None


def test_beating_a_cancelled_run_reports_the_cancellation():
    with connection() as conn:
        job = _claimed(conn)
        runs.cancel(conn, job["run_id"], USER)

        assert runs.beat(conn, job["run_id"]) == "cancelled"


def test_beating_a_cancelled_run_does_not_revive_its_heartbeat():
    """A cancelled run is finished. Moving its heartbeat would make the
    reaper think a worker still owns it."""
    with connection() as conn:
        job = _claimed(conn)
        _stop_beating(conn, job["run_id"], 600)
        before = runs.get(conn, job["run_id"], USER)["heartbeat_at"]
        runs.cancel(conn, job["run_id"], USER)

        runs.beat(conn, job["run_id"])

        assert runs.get(conn, job["run_id"], USER)["heartbeat_at"] == before


# --- a straggler must not overwrite a finished run -------------------------
#
# `complete` and `cancel` both guard on status; `fail` did not. The reaper
# requeues a run, worker B answers it and stores the message, and zombie
# worker A then raises somewhere and calls fail() -- which overwrote the
# row unconditionally. The thread held a correct answer while the run told
# the reader "Research failed."


def test_failing_a_run_that_already_succeeded_changes_nothing():
    with connection() as conn:
        job = _claimed(conn)
        runs.finish(conn, job["run_id"], {"text": "the answer"})

        assert runs.fail(conn, job["run_id"], "internal_error", "Research failed.") is False

        run = runs.get(conn, job["run_id"], USER)
        assert run["status"] == "done"
        assert run["error"] is None


def test_failing_a_cancelled_run_does_not_relabel_the_readers_decision():
    with connection() as conn:
        job = _claimed(conn)
        runs.cancel(conn, job["run_id"], USER)

        assert runs.fail(conn, job["run_id"], "internal_error", "Research failed.") is False
        assert runs.get(conn, job["run_id"], USER)["status"] == "cancelled"


def test_a_run_that_succeeded_gains_no_second_terminal_event():
    """A stream replaying two terminal events shows the reader an answer
    and then an error about the same run."""
    with connection() as conn:
        job = _claimed(conn)
        runs.finish(conn, job["run_id"], {"text": "the answer"})
        runs.fail(conn, job["run_id"], "internal_error", "Research failed.")

        kinds = [e["kind"] for e in runs.events_after(conn, job["run_id"], 0)]

    assert kinds.count("done") == 1
    assert "error" not in kinds


def test_a_running_run_still_fails_normally():
    with connection() as conn:
        job = _claimed(conn)
        assert runs.fail(conn, job["run_id"], "timeout", "Too slow.") is True
        assert runs.get(conn, job["run_id"], USER)["status"] == "failed"


# --- two reapers must not fight over the same row --------------------------
#
# Every idle worker sweeps, so with more than one worker two reapers
# overlap. Committing inside the loop released the FOR UPDATE locks on the
# rows not yet handled, so the second reaper could requeue a run the first
# had already requeued -- and which a worker had since claimed and set back
# to running. That yanks a live job away and hands it to a second worker:
# `complete` keeps only one answer, but the model budget is spent twice.


def test_a_run_reclaimed_since_the_sweep_began_is_left_alone():
    with connection() as conn:
        job = _claimed(conn)
        _stop_beating(conn, job["run_id"], 600)

        runs.reap(conn, stale_after=60)
        reclaimed = runs.claim(conn, ("research",))
        assert reclaimed["run_id"] == job["run_id"]

        # A second reaper, sweeping moments later, sees a fresh heartbeat.
        assert runs.reap(conn, stale_after=60) == []
        assert runs.get(conn, job["run_id"], USER)["status"] == "running"


def test_the_requeue_matches_on_the_state_it_is_changing():
    """The guard has to be in the statement, not in a snapshot taken
    earlier: whatever the reaper saw when it looked, it must only move a
    row that is still stale and still running when it writes."""
    import inspect

    source = inspect.getsource(runs.reap)
    assert "status = 'running'" in source
    assert "heartbeat_at <" in source


def test_many_stale_runs_are_all_swept():
    with connection() as conn:
        ids = []
        for _ in range(4):
            job = _claimed(conn)
            _stop_beating(conn, job["run_id"], 600)
            ids.append(job["run_id"])

        swept = runs.reap(conn, stale_after=60)

    assert sorted(swept) == sorted(ids)
