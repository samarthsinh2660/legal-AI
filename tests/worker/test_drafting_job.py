"""The drafting job.

Its own file because the risk is different from research: drafting is one
long model call with no nodes to pause between, so the seam that keeps a
research run's heartbeat alive does not exist here.
"""

from __future__ import annotations

import pytest

from api.databases.postgres import connection
from api.drafts import repository as drafts
from api.runs import repository as runs
from api.threads.repository import add_message, create_thread, ensure_thread_schema
from worker import drafting

USER = "test-user-draftjob"


@pytest.fixture(autouse=True)
def _clean():
    with connection() as conn:
        ensure_thread_schema(conn)
        runs.ensure_run_schema(conn)
        drafts.ensure_draft_schema(conn)
        conn.execute("DELETE FROM threads WHERE user_id LIKE 'test-user-draftjob%'")
        conn.commit()
    yield
    with connection() as conn:
        conn.execute("DELETE FROM threads WHERE user_id LIKE 'test-user-draftjob%'")
        conn.commit()


def _job(conn):
    thread = create_thread(conn, USER, title="Verma v. Malhotra")
    add_message(conn, thread.thread_id, "user", "the cheque bounced")
    add_message(
        conn, thread.thread_id, "assistant", "Section 138 applies.",
        answer={"key_elements": [
            {"text": "Dishonour is an offence.", "evidence_ids": ["act:2189:sec-138"]}
        ]},
    )
    draft_id = drafts.start(conn, thread.thread_id)
    runs.enqueue(conn, thread.thread_id, USER, "draft", {"draft_id": draft_id})
    conn.commit()
    return runs.claim(conn, ("draft",))


def test_a_draft_beats_while_the_model_call_is_running(monkeypatch):
    """Without this the heartbeat is set once by `claim` and never again,
    so a draft slower than STALE_AFTER_SECONDS -- which the model chain's
    rate-limit backoff makes plausible -- is requeued while it is still
    being written, and two workers finish the same draft row."""
    beats = []
    monkeypatch.setattr(drafting.runs, "beat",
                        lambda _conn, run_id: beats.append(run_id) or "running")

    def slow_draft(*_args, **_kwargs):
        raise RuntimeError("stop here; the beat is what is being checked")

    monkeypatch.setattr("legal_ai.agents.drafter.draft", slow_draft)

    with connection() as conn:
        job = _job(conn)
    drafting.run(job)

    assert job["run_id"] in beats


def test_a_cancelled_draft_stops_before_the_model_call(monkeypatch):
    """The cheapest cancellation: a draft that has not started costs
    nothing to abandon."""
    called = []
    monkeypatch.setattr("legal_ai.agents.drafter.draft",
                        lambda *a, **k: called.append(1))

    with connection() as conn:
        job = _job(conn)
        runs.cancel(conn, job["run_id"], USER)
    drafting.run(job)

    assert called == []
    with connection() as conn:
        assert drafts.get(conn, job["payload"]["draft_id"], USER)["status"] != "done"
