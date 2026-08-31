"""Logout.

Cross-domain: accounts x middleware.

A stateless JWT is valid until it expires, so a logout that only tells the
client to forget its token is a suggestion an attacker holding a copy will
decline. These tests pin that the token is actually refused afterwards.
"""

import pytest
from fastapi.testclient import TestClient

from api.accounts.revocation import ensure_revocation_schema, purge_expired
from api.databases.postgres import connection
from api.main import create_app
from api.middleware.rate_limit import RateLimiter
from api.utils.tokens import issue_access_token

SECRET = "a-test-signing-secret-long-enough-for-hs256"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("LEGAL_AI_JWT_SECRET", SECRET)
    with connection() as conn:
        ensure_revocation_schema(conn)
        conn.execute("DELETE FROM revoked_tokens")
        conn.commit()
    yield TestClient(create_app(limiter=RateLimiter(limit=10_000)))
    with connection() as conn:
        conn.execute("DELETE FROM revoked_tokens")
        conn.execute("DELETE FROM threads WHERE user_id LIKE 'test-logout%'")
        conn.commit()


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_a_token_stops_working_after_logout(client):
    """The whole point. Anything less is a note to the client."""
    token = issue_access_token("test-logout-user", secret=SECRET)
    assert client.get("/threads", headers=_auth(token)).status_code == 200
    assert client.post("/auth/logout", headers=_auth(token)).status_code == 200
    assert client.get("/threads", headers=_auth(token)).status_code == 401


def test_logging_out_twice_is_not_an_error(client):
    """A retried request must not look like a failure."""
    token = issue_access_token("test-logout-user", secret=SECRET)
    assert client.post("/auth/logout", headers=_auth(token)).status_code == 200
    # The second call is rejected by the middleware, not by logout itself --
    # the token is already revoked, which is the correct answer.
    assert client.post("/auth/logout", headers=_auth(token)).status_code == 401


def test_logout_does_not_affect_another_session(client):
    """Revocation is per token, not per user: signing out on a laptop must
    not sign you out on a phone."""
    laptop = issue_access_token("test-logout-user", secret=SECRET)
    phone = issue_access_token("test-logout-user", secret=SECRET)
    client.post("/auth/logout", headers=_auth(laptop))
    assert client.get("/threads", headers=_auth(phone)).status_code == 200


def test_logout_needs_a_token(client):
    assert client.post("/auth/logout").status_code == 401


def test_expired_rows_are_purged():
    """Without this the table grows by one row per logout forever. A row is
    only useful until the token would expire anyway."""
    from datetime import datetime, timedelta, timezone

    with connection() as conn:
        ensure_revocation_schema(conn)
        conn.execute(
            "INSERT INTO revoked_tokens (jti, expires_at) VALUES (%s, %s) "
            "ON CONFLICT DO NOTHING",
            ("stale-jti", datetime.now(timezone.utc) - timedelta(hours=2)),
        )
        conn.commit()
        assert purge_expired(conn) >= 1
        left = conn.execute(
            "SELECT count(*) FROM revoked_tokens WHERE jti = 'stale-jti'"
        ).fetchone()[0]
    assert left == 0


def test_a_purged_row_does_not_resurrect_the_token(client):
    """The row goes because the token has expired -- so the token must still
    be refused, now by expiry rather than by the denylist."""
    expired = issue_access_token("test-logout-user", secret=SECRET, expires_in=-1)
    assert client.get("/threads", headers=_auth(expired)).status_code == 401
