"""The loop that claims jobs.

Two mechanisms, and only the sweep is load-bearing: `LISTEN` decides whether
a job starts in milliseconds or on the next sweep, never whether it starts.
Both are tested here, because the second is what makes the first safe to
depend on.
"""

from __future__ import annotations

import time

import pytest

from api.databases.postgres import connection
from api.runs import repository as runs
from api.threads.repository import create_thread, ensure_thread_schema
from worker.loop import Worker

USER = "test-user-loop"

# A kind nothing else serves.
#
# The queue is shared: a worker container against the same database will
# claim a 'research' job out from under these tests, and they then fail
# having proved nothing. Naming a private kind is also what the claim query
# is for -- a worker takes only what it can serve.
KIND = "test-loop"
OTHER_KIND = "test-loop-other"


@pytest.fixture(autouse=True)
def _clean():
    with connection() as conn:
        ensure_thread_schema(conn)
        runs.ensure_run_schema(conn)
        conn.execute("DELETE FROM threads WHERE user_id LIKE 'test-user-loop%'")
        conn.commit()
    yield
    with connection() as conn:
        conn.execute("DELETE FROM threads WHERE user_id LIKE 'test-user-loop%'")
        conn.commit()


def _handled(monkeypatch) -> list:
    """Replace the job handlers with a recorder."""
    import worker.loop as loop_module

    seen = []
    monkeypatch.setattr(loop_module, "_dispatch", seen.append)
    return seen


def test_an_empty_queue_is_not_a_job(monkeypatch):
    _handled(monkeypatch)
    assert Worker(kinds=(KIND,)).run_once() is False


def test_a_queued_job_is_claimed_and_dispatched(monkeypatch):
    seen = _handled(monkeypatch)
    with connection() as conn:
        thread = create_thread(conn, USER)
        run_id = runs.enqueue(conn, thread.thread_id, USER, KIND, {"q": 1})

    assert Worker(kinds=(KIND,)).run_once() is True
    assert [job["run_id"] for job in seen] == [run_id]


def test_a_worker_takes_only_the_kinds_it_serves(monkeypatch):
    seen = _handled(monkeypatch)
    with connection() as conn:
        thread = create_thread(conn, USER)
        runs.enqueue(conn, thread.thread_id, USER, OTHER_KIND, {})

    assert Worker(kinds=(KIND,)).run_once() is False
    assert seen == []


def test_a_second_worker_finds_nothing_left(monkeypatch):
    """The claim is what makes a second worker free rather than a hazard."""
    seen = _handled(monkeypatch)
    with connection() as conn:
        thread = create_thread(conn, USER)
        runs.enqueue(conn, thread.thread_id, USER, KIND, {})

    assert Worker(kinds=(KIND,)).run_once() is True
    assert Worker(kinds=(KIND,)).run_once() is False
    assert len(seen) == 1


def test_stopping_finishes_the_job_in_hand_rather_than_dropping_it(monkeypatch):
    """A run killed mid-model-call has already been paid for, and the row it
    leaves says "running" with nothing coming."""
    import worker.loop as loop_module

    worker = Worker(kinds=(KIND,))
    finished = []

    def slow(job):
        worker.stop()
        finished.append(job["run_id"])

    monkeypatch.setattr(loop_module, "_dispatch", slow)
    with connection() as conn:
        thread = create_thread(conn, USER)
        run_id = runs.enqueue(conn, thread.thread_id, USER, KIND, {})

    worker.run_forever()

    assert finished == [run_id]


def test_an_idle_worker_is_woken_by_a_job_rather_than_waiting_it_out(monkeypatch):
    """`NOTIFY` is why a queued job starts in milliseconds. It is not what
    makes it start -- that is the sweep -- so this measures latency, which
    is the only thing the notification is for."""
    import worker.loop as loop_module

    # Far longer than the wait should actually take, so a pass cannot be the
    # sweep timing out.
    monkeypatch.setattr(loop_module, "IDLE_SECONDS", 30.0)
    worker = Worker(kinds=(KIND,))
    # The listener has to be established before the NOTIFY is raised; a
    # notification to nobody is not stored.
    worker._listen()

    with connection() as conn:
        thread = create_thread(conn, USER)
        runs.enqueue(conn, thread.thread_id, USER, KIND, {})

    started = time.monotonic()
    worker._wait()
    elapsed = time.monotonic() - started
    worker._close_listener()

    assert elapsed < 5.0, f"waited {elapsed:.1f}s for a notification"


# --- the first question must not pay for the models ------------------------
#
# Measured 2026-09-06: the first turn after a worker started took 108s, of
# which ~21s was 69 HTTP round-trips to huggingface.co revalidating an
# embedder already on disk, plus the load itself. The second and third turns
# on the same worker took 18s and 40s. The cost is real and it is paid once
# per process -- so it should be paid before the process says it is ready,
# not by whoever asks first.


def test_the_models_are_loaded_before_any_job_is_claimed(monkeypatch):
    import worker.loop as loop_module

    order = []
    monkeypatch.setattr(loop_module, "_warm_models", lambda: order.append("warm"))
    monkeypatch.setattr(loop_module, "_dispatch", lambda job: order.append("job"))

    with connection() as conn:
        thread = create_thread(conn, USER)
        runs.enqueue(conn, thread.thread_id, USER, KIND, {})

    worker = Worker(kinds=(KIND,))
    worker.warm()
    worker.run_once()

    assert order == ["warm", "job"]


def test_a_worker_still_starts_when_the_models_cannot_load(monkeypatch):
    """A model host that is down must not stop the worker booting: the
    embedder is needed by research, and small talk and drafting do not
    touch it."""
    import worker.loop as loop_module

    def explodes():
        raise RuntimeError("huggingface.co is unreachable")

    monkeypatch.setattr(loop_module, "_warm_models", explodes)

    # The whole assertion: it returns rather than raising.
    Worker(kinds=(KIND,)).warm()


# --- the reaper -------------------------------------------------------------
#
# It runs on the idle sweep rather than in a process of its own. A worker
# with nothing to do is exactly when a stale row is worth looking for, and a
# separate reaper would be another thing to deploy, watch and restart for a
# query that takes an index scan.
#
# The one case this does not cover is a deployment with no workers at all --
# where nothing is running either, so nothing can have been abandoned.


def test_an_idle_worker_reaps(monkeypatch):
    import worker.loop as loop_module

    swept = []
    monkeypatch.setattr(loop_module.runs, "reap",
                        lambda _conn, stale_after: swept.append(stale_after) or [])
    monkeypatch.setattr(loop_module, "IDLE_SECONDS", 0.1)

    worker = Worker(kinds=(KIND,))
    worker._wait()

    assert swept == [loop_module.STALE_AFTER_SECONDS]


def test_the_stale_window_is_longer_than_a_run_is_allowed_to_take():
    """A worker deep in a model call must not be declared dead while it is
    working -- the answer it goes on to store would land on a run somebody
    else had already been given."""
    import worker.graph as graph_module
    import worker.loop as loop_module

    assert loop_module.STALE_AFTER_SECONDS > graph_module.DEFAULT_TIMEOUT_SECONDS


def test_a_worker_that_cannot_reap_still_takes_jobs(monkeypatch):
    """The sweep is maintenance. A database hiccup in it must not stop the
    thing the worker is actually for."""
    import worker.loop as loop_module

    def explodes(_conn, stale_after):
        raise RuntimeError("the sweep failed")

    monkeypatch.setattr(loop_module.runs, "reap", explodes)
    monkeypatch.setattr(loop_module, "IDLE_SECONDS", 0.1)
    seen = _handled(monkeypatch)

    worker = Worker(kinds=(KIND,))
    worker._wait()

    with connection() as conn:
        thread = create_thread(conn, USER)
        runs.enqueue(conn, thread.thread_id, USER, KIND, {})
    assert worker.run_once() is True
