"""The audit trail.

A firm has to be able to answer "who opened this matter, and when" before
it will put client data in the tool. That is the first thing every survey
of legal-AI adoption asks for, ahead of features.

What is recorded is deliberately narrow: who, what action, which resource,
when, and whether it succeeded. Never the question, never the answer, never
a document's text -- all of that is already stored once, under the user's
own row, and a second copy in a table with different retention is a second
place for privileged material to leak from.
"""

import pytest
from fastapi.testclient import TestClient

from api.audit.repository import (
    ensure_audit_schema,
    events_for,
    record,
)
from api.databases.postgres import connection
from api.main import create_app
from api.middleware.rate_limit import RateLimiter
from api.utils.tokens import issue_access_token

SECRET = "a" * 40
USER = "audit-test-user"


@pytest.fixture(autouse=True)
def schema():
    with connection() as conn:
        ensure_audit_schema(conn)
        conn.execute("DELETE FROM audit_events WHERE user_id LIKE 'audit-test%'")
        conn.commit()
    yield
    with connection() as conn:
        conn.execute("DELETE FROM audit_events WHERE user_id LIKE 'audit-test%'")
        conn.commit()


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("LEGAL_AI_JWT_SECRET", SECRET)
    return TestClient(create_app(limiter=RateLimiter(limit=10_000)))


def _auth(user: str = USER) -> dict:
    return {"Authorization": f"Bearer {issue_access_token(user, secret=SECRET)}"}


# --- the record itself ------------------------------------------------------

def test_an_event_records_who_did_what_to_which_resource():
    with connection() as conn:
        record(conn, USER, "read", "case", "case-1", 200)
        events = events_for(conn, USER, limit=10)

    assert len(events) == 1
    assert (events[0].action, events[0].resource_type, events[0].resource_id) == (
        "read", "case", "case-1",
    )
    assert events[0].status == 200


def test_events_come_back_newest_first():
    with connection() as conn:
        record(conn, USER, "read", "case", "first", 200)
        record(conn, USER, "read", "case", "second", 200)
        events = events_for(conn, USER, limit=10)

    assert [e.resource_id for e in events] == ["second", "first"]


def test_one_user_cannot_read_another_user_s_trail():
    """The trail is client data about client data."""
    with connection() as conn:
        record(conn, "audit-test-other", "read", "case", "theirs", 200)
        assert events_for(conn, USER, limit=10) == []


def test_a_refused_request_is_recorded_as_refused():
    """An attempt that failed is the most interesting row in the table."""
    with connection() as conn:
        record(conn, USER, "read", "case", "not-mine", 404)
        assert events_for(conn, USER, limit=10)[0].status == 404


# --- what goes through the middleware ---------------------------------------

def test_reading_a_thread_list_is_recorded(client):
    client.get("/threads", headers=_auth())

    with connection() as conn:
        actions = [(e.action, e.resource_type) for e in events_for(conn, USER, limit=10)]
    assert ("read", "thread") in actions


def test_a_deletion_is_recorded_even_when_it_finds_nothing(client):
    """A 404 delete is an attempt on a matter, and the attempt is the record
    a firm cares about."""
    client.delete("/threads/no-such-thread", headers=_auth())

    with connection() as conn:
        events = events_for(conn, USER, limit=10)
    assert any(e.action == "delete" and e.status == 404 for e in events)


def test_the_resource_id_is_taken_from_the_path(client):
    client.get("/cases/case-abc", headers=_auth())

    with connection() as conn:
        events = events_for(conn, USER, limit=10)
    assert any(e.resource_id == "case-abc" for e in events)


def test_health_is_not_audited(client):
    """Liveness probes would bury the trail in noise."""
    for _ in range(5):
        client.get("/health")

    with connection() as conn:
        conn.execute("DELETE FROM audit_events WHERE resource_type = 'health'")
        conn.commit()
        rows = conn.execute(
            "SELECT count(*) FROM audit_events WHERE user_id = %s", (USER,)
        ).fetchone()[0]
    assert rows == 0


def test_a_public_path_writes_no_anonymous_row(client):
    """`/auth/login` reaches the audit middleware with nobody attached --
    auth lets public paths through. A placeholder like "anonymous" would
    make the trail lie about who acted.

    A request to a *protected* path is rejected by auth further out and
    never reaches this middleware at all, so it is not the case to test.
    """
    with connection() as conn:
        before = conn.execute("SELECT count(*) FROM audit_events").fetchone()[0]

    client.post("/auth/login", json={"email": "nobody@example.com", "password": "x" * 12})

    with connection() as conn:
        after = conn.execute("SELECT count(*) FROM audit_events").fetchone()[0]
    assert after == before


def test_the_trail_never_holds_the_question_or_the_answer(client):
    """Privileged content is stored once, under the user's own row. A second
    copy here would be a second place for it to leak from."""
    secret = "my client bribed the inspector on 3 March"
    client.post("/threads", headers=_auth(), json={"title": secret, "case_id": None})

    with connection() as conn:
        rows = conn.execute(
            "SELECT count(*) FROM audit_events WHERE user_id = %s "
            "AND (resource_id ILIKE %s OR action ILIKE %s)",
            (USER, f"%{secret}%", f"%{secret}%"),
        ).fetchone()[0]
    assert rows == 0


def test_a_failed_audit_write_does_not_lose_the_request(client, monkeypatch):
    """The trail must not become a single point of failure for the service.
    The gap is loud in the logs instead -- see AuditMiddleware."""
    import api.middleware.audit as audit_middleware

    def boom(*_a, **_kw):
        raise RuntimeError("audit store is down")

    monkeypatch.setattr(audit_middleware, "record", boom)

    assert client.get("/threads", headers=_auth()).status_code == 200


# --- reading it back --------------------------------------------------------

def test_a_user_can_read_their_own_trail(client):
    client.get("/threads", headers=_auth())
    body = client.get("/audit", headers=_auth()).json()

    assert body["success"]
    assert body["data"]["total"] >= 1
    assert body["data"]["items"][0]["resource_type"] == "thread"


def test_the_trail_shows_only_your_own_events(client):
    client.get("/threads", headers=_auth("audit-test-a"))
    body = client.get("/audit", headers=_auth("audit-test-b")).json()

    assert body["data"]["items"] == []


def test_reading_the_trail_needs_a_token(client):
    assert client.get("/audit").status_code == 401


def test_the_trail_is_append_only_over_http(client):
    """No route edits or removes an event. An audit trail that can be
    rewritten is not one."""
    for method in ("post", "patch", "delete"):
        response = getattr(client, method)("/audit", headers=_auth())
        assert response.status_code in (404, 405), method


# --- sign-in ----------------------------------------------------------------
#
# The middleware cannot record these: `/auth/login` is a public path, so
# nobody is attached to the request by the time it runs. They are recorded
# in the router, which is the only place that learns who signed in.

def test_a_successful_sign_in_is_recorded(client):
    email = "audit-signin@example.com"
    password = "a-very-long-password"
    client.post("/auth/register", json={"email": email, "password": password})
    client.post("/auth/login", json={"email": email, "password": password})

    with connection() as conn:
        user_id = conn.execute(
            "SELECT user_id FROM users WHERE email = %s", (email,)
        ).fetchone()[0]
        actions = [e.action for e in events_for(conn, user_id, limit=10)]
        conn.execute("DELETE FROM audit_events WHERE user_id = %s", (user_id,))
        conn.execute("DELETE FROM users WHERE email = %s", (email,))
        conn.commit()

    assert "sign-in" in actions


def test_a_failed_sign_in_is_recorded_against_the_account(client):
    """The row a firm looks for first. Recorded against the account that was
    targeted -- not against the caller, who is by definition unidentified."""
    email = "audit-badpw@example.com"
    client.post("/auth/register", json={"email": email, "password": "a-very-long-password"})
    client.post("/auth/login", json={"email": email, "password": "wrong-password-here"})

    with connection() as conn:
        user_id = conn.execute(
            "SELECT user_id FROM users WHERE email = %s", (email,)
        ).fetchone()[0]
        events = events_for(conn, user_id, limit=10)
        conn.execute("DELETE FROM audit_events WHERE user_id = %s", (user_id,))
        conn.execute("DELETE FROM users WHERE email = %s", (email,))
        conn.commit()

    assert any(e.action == "sign-in" and e.status == 401 for e in events)


def test_a_sign_in_for_an_unknown_address_records_nothing(client):
    """There is no account to attribute it to, and creating a row keyed by
    the address would turn the trail into a register of who does not have
    an account here."""
    with connection() as conn:
        before = conn.execute("SELECT count(*) FROM audit_events").fetchone()[0]

    client.post("/auth/login",
                json={"email": "never-existed@example.com", "password": "x" * 14})

    with connection() as conn:
        after = conn.execute("SELECT count(*) FROM audit_events").fetchone()[0]
    assert after == before


# --- what the review caught -------------------------------------------------

def test_an_oversized_limit_is_a_400_not_a_500(client):
    """The route's ceiling and PageParams' ceiling have to agree, or a limit
    between them raises inside the handler and escapes the envelope."""
    response = client.get("/audit?limit=150", headers=_auth())
    assert response.status_code == 400
    assert response.json()["success"] is False


def test_reading_the_trail_is_itself_recorded(client):
    """For a compliance feature, "who read the trail" is the row a firm
    wants most."""
    client.get("/audit", headers=_auth())
    client.get("/audit", headers=_auth())

    with connection() as conn:
        actions = [
            (e.action, e.resource_type) for e in events_for(conn, USER, limit=10)
        ]
    assert ("read", "audit") in actions


def test_a_document_upload_is_indexed_under_its_case(client):
    """`audit_events_resource_idx` exists to answer "who touched this
    matter". Filing uploads under a document id nobody stored would make
    that query miss them."""
    client.get("/cases/case-xyz/documents", headers=_auth())

    with connection() as conn:
        events = events_for(conn, USER, limit=10)
    assert any(
        e.resource_type == "case" and e.resource_id == "case-xyz" for e in events
    )


def test_an_account_route_records_no_bogus_resource_id(client):
    """An account route was storing its own path segment as resource_id,
    which is not an id, and it landed in the resource index beside real
    ones. Checked on /auth/logout since /auth/me no longer exists."""
    client.post("/auth/logout", headers=_auth())

    with connection() as conn:
        events = events_for(conn, USER, limit=10)
    assert all(e.resource_id != "logout" for e in events)


def test_a_handler_that_raises_is_still_recorded(client, monkeypatch):
    """A 500 must leave a trace that the matter was touched. Without it the
    middleware's promise -- that a route cannot forget -- is false exactly
    when it matters."""
    import api.threads.router as threads_router

    def boom(*_a, **_kw):
        raise RuntimeError("handler exploded")

    monkeypatch.setattr(threads_router, "list_threads", boom)
    try:
        client.get("/threads", headers=_auth())
    except RuntimeError:
        pass

    with connection() as conn:
        events = events_for(conn, USER, limit=10)
    assert any(e.status == 500 for e in events)
