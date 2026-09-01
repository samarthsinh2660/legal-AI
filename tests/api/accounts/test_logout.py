"""Logout.

There is no server-side denylist: the route ends the session on the client
and nothing else. These tests pin that contract honestly -- including the
part that is a limitation, because a test suite that only asserts the happy
path would let someone later read this route as revocation.
"""

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from api.middleware.rate_limit import RateLimiter
from api.utils.tokens import issue_access_token

SECRET = "a" * 40


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("LEGAL_AI_JWT_SECRET", SECRET)
    return TestClient(create_app(limiter=RateLimiter(limit=10_000)))


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_logout_needs_a_token_like_every_other_route(client):
    assert client.post("/auth/logout").status_code == 401


def test_logout_confirms_the_token_was_real(client):
    token = issue_access_token("test-logout-user", secret=SECRET)
    response = client.post("/auth/logout", headers=_auth(token))
    assert response.status_code == 200
    assert response.json()["data"]["logged_out"] is True


def test_logging_out_twice_is_not_an_error(client):
    """A retried request must not look like a failure."""
    token = issue_access_token("test-logout-user", secret=SECRET)
    for _ in range(2):
        assert client.post("/auth/logout", headers=_auth(token)).status_code == 200


def test_the_token_still_works_after_logout(client):
    """Not a bug -- the documented limitation. Nothing invalidates a signed
    token before `exp`, so a copy of it keeps working, and
    LEGAL_AI_JWT_EXPIRES_IN is the only thing bounding that. If a denylist
    is ever added, this is the test that should flip."""
    token = issue_access_token("test-logout-user", secret=SECRET)
    client.post("/auth/logout", headers=_auth(token))
    assert client.get("/threads", headers=_auth(token)).status_code != 401


def test_an_expired_token_is_refused(client):
    """The bound that does hold."""
    expired = issue_access_token("test-logout-user", secret=SECRET, expires_in=-1)
    assert client.get("/threads", headers=_auth(expired)).status_code == 401
