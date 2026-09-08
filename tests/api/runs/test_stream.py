"""Watching a run over SSE.

The route a reopened tab, a second device and a recovered connection all
take. What it must guarantee is that attaching costs nothing but the events
actually missed -- `Last-Event-ID` is SSE's own mechanism for that, and
`run_events` is what makes replay possible at all.

Driven through the app rather than the generator, because the header
handling and the framing are half of what can go wrong.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.databases.postgres import connection
from api.main import create_app
from api.middleware.rate_limit import RateLimiter
from api.runs import repository as runs
from api.threads.repository import create_thread, ensure_thread_schema
from api.utils.tokens import issue_access_token

SECRET = "a-test-signing-secret-long-enough-for-hs256"
USER, OTHER = "test-stream-mine", "test-stream-theirs"


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setenv("LEGAL_AI_JWT_SECRET", SECRET)
    with connection() as conn:
        ensure_thread_schema(conn)
        runs.ensure_run_schema(conn)
        conn.execute("DELETE FROM threads WHERE user_id LIKE 'test-stream-%'")
        conn.commit()
    yield create_app(limiter=RateLimiter(limit=10_000))
    with connection() as conn:
        conn.execute("DELETE FROM threads WHERE user_id LIKE 'test-stream-%'")
        conn.commit()


def _client(app, user=USER):
    client = TestClient(app)
    client.headers.update(
        {"Authorization": f"Bearer {issue_access_token(user, secret=SECRET)}"}
    )
    return client


def _finished_run(steps=("research", "analyst")):
    """A run that is already over, so the stream replays and closes."""
    with connection() as conn:
        thread = create_thread(conn, USER)
        runs.enqueue(conn, thread.thread_id, USER, "research", {})
        # Claimed, because only a running run can finish -- that is what
        # lets the reaper hand an abandoned one to somebody else.
        run_id = runs.claim(conn, ("research",))["run_id"]
        for node in steps:
            runs.step(conn, run_id, node, f"Doing {node}")
        runs.finish(conn, run_id, {"text": "the answer"})
    return run_id


def _frames(body: str) -> list[dict]:
    """The SSE frames in `body`, as `{id, event, data}`."""
    parsed = []
    for frame in body.split("\n\n"):
        fields = {}
        for line in frame.splitlines():
            if line.startswith(("id:", "event:", "data:")):
                name, _, value = line.partition(":")
                fields[name] = value.strip()
        if fields:
            parsed.append(fields)
    return parsed


def test_a_stream_replays_the_whole_run_and_closes(app):
    run_id = _finished_run()
    response = _client(app).get(f"/runs/{run_id}/stream")

    frames = _frames(response.text)
    assert [frame["event"] for frame in frames] == ["step", "step", "done"]
    assert [frame["id"] for frame in frames] == ["1", "2", "3"]


def test_a_reconnect_gets_only_what_it_missed(app):
    """The point of the id. Replaying the whole run on every reconnect would
    show a reader the same steps twice."""
    run_id = _finished_run()
    response = _client(app).get(
        f"/runs/{run_id}/stream", headers={"Last-Event-ID": "2"}
    )

    frames = _frames(response.text)
    assert [frame["id"] for frame in frames] == ["3"]
    assert "the answer" in frames[0]["data"]


def test_an_unreadable_last_event_id_replays_everything(app):
    """Replaying too much is cheap; losing an event is not."""
    run_id = _finished_run()
    response = _client(app).get(
        f"/runs/{run_id}/stream", headers={"Last-Event-ID": "not-a-number"}
    )

    assert len(_frames(response.text)) == 3


def test_a_failed_run_ends_the_stream_with_its_reason(app):
    with connection() as conn:
        thread = create_thread(conn, USER)
        runs.enqueue(conn, thread.thread_id, USER, "research", {})
        run_id = runs.claim(conn, ("research",))["run_id"]
        runs.fail(conn, run_id, "timeout", "Research did not finish in time.")

    frames = _frames(_client(app).get(f"/runs/{run_id}/stream").text)

    assert frames[-1]["event"] == "error"
    assert "did not finish" in frames[-1]["data"]


def test_another_users_run_is_a_404(app):
    run_id = _finished_run()
    response = _client(app, OTHER).get(f"/runs/{run_id}/stream")
    assert response.status_code == 404


def test_a_run_can_be_read_without_watching_it(app):
    run_id = _finished_run()
    body = _client(app).get(f"/runs/{run_id}").json()

    assert body["data"]["status"] == "done"
    assert body["data"]["current_step"] == "analyst"


# --- the browser's own preflight -------------------------------------------


def test_the_resume_header_survives_a_cors_preflight(app):
    """`Last-Event-ID` is a custom header, so a cross-origin reconnect is
    blocked at the preflight unless it is named in the allow-list.

    Nothing in the test suite could catch this: the client tests mock
    `fetch`, so no preflight is ever made, and the QA suite uses curl, which
    does not make one either. Found by reading the OPTIONS response against
    the running API, 2026-09-06 -- the frontend on :3001 talking to the API
    on :8000 is cross-origin, and so is every deployment.
    """
    import os

    from api.main import create_app
    from api.middleware.rate_limit import RateLimiter

    os.environ["LEGAL_AI_CORS_ORIGINS"] = "http://localhost:3001"
    try:
        client = TestClient(create_app(limiter=RateLimiter(limit=10_000)))
        response = client.options(
            "/runs/anything/stream",
            headers={
                "Origin": "http://localhost:3001",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "authorization,last-event-id",
            },
        )
    finally:
        os.environ.pop("LEGAL_AI_CORS_ORIGINS", None)

    assert response.status_code == 200
    allowed = response.headers["access-control-allow-headers"].lower()
    assert "last-event-id" in allowed


# --- cancelling ------------------------------------------------------------


def test_a_reader_can_cancel_their_own_run(app):
    with connection() as conn:
        thread = create_thread(conn, USER)
        run_id = runs.enqueue(conn, thread.thread_id, USER, "research", {})

    response = _client(app).post(f"/runs/{run_id}/cancel")
    assert response.status_code == 200

    with connection() as conn:
        assert runs.get(conn, run_id, USER)["status"] == "cancelled"


def test_cancelling_ends_the_stream_with_a_reason(app):
    """A stream that just stopped would look like a dropped connection, and
    the client would reconnect to a run that is not coming back."""
    with connection() as conn:
        thread = create_thread(conn, USER)
        run_id = runs.enqueue(conn, thread.thread_id, USER, "research", {})
    client = _client(app)
    client.post(f"/runs/{run_id}/cancel")

    frames = _frames(client.get(f"/runs/{run_id}/stream").text)
    assert frames[-1]["event"] == "error"
    assert "cancelled" in frames[-1]["data"]


def test_another_users_run_cannot_be_cancelled(app):
    with connection() as conn:
        thread = create_thread(conn, USER)
        run_id = runs.enqueue(conn, thread.thread_id, USER, "research", {})

    assert _client(app, OTHER).post(f"/runs/{run_id}/cancel").status_code == 404
    with connection() as conn:
        assert runs.get(conn, run_id, USER)["status"] == "queued"


def test_cancelling_a_finished_run_is_refused_rather_than_silently_ignored(app):
    """The answer is stored and paid for; the client should learn that its
    cancel arrived too late rather than believe it worked."""
    run_id = _finished_run()
    assert _client(app).post(f"/runs/{run_id}/cancel").status_code == 409


def test_a_run_that_finishes_between_the_two_reads_still_sends_its_answer(app):
    """The generator read events, then status. `_reply` commits the status
    change and the `done` event together, so a commit landing between the
    two reads left `pending` empty and `status` done -- and the stream
    closed with no terminal frame at all.

    Simulated by finishing the run inside `events_after`, which is exactly
    that window.
    """
    from api.runs import router as runs_router

    with connection() as conn:
        thread = create_thread(conn, USER)
        runs.enqueue(conn, thread.thread_id, USER, "research", {})
        run_id = runs.claim(conn, ("research",))["run_id"]

    real_events_after = runs_router.runs.events_after
    fired = {"done": False}

    def finish_midway(conn, rid, after):
        pending = real_events_after(conn, rid, after)
        if not fired["done"]:
            fired["done"] = True
            with connection() as other:
                runs.finish(other, rid, {"text": "the answer"})
        return pending

    runs_router.runs.events_after = finish_midway
    try:
        frames = _frames(_client(app).get(f"/runs/{run_id}/stream").text)
    finally:
        runs_router.runs.events_after = real_events_after

    assert frames, "the stream closed with no frames at all"
    assert frames[-1]["event"] == "done"
    assert "the answer" in frames[-1]["data"]
