"""Register, log in, and the identity check every protected route runs.

Cross-domain: api x accounts.

The shared API key answered "may this caller talk to the service". It could
not answer "whose cases are these", which is the question that matters once
a row has an owner. These tests pin the replacement, and most of them are
about refusing rather than allowing -- an auth layer earns its keep by what
it turns away.

Two properties are load-bearing and neither is visible in a happy-path test:
a login must not reveal which email addresses are registered, and a missing
signing secret must close the service rather than open it.
"""

import pytest
from fastapi.testclient import TestClient

from api.accounts.repository import ensure_account_schema
from api.main import create_app
from api.middleware.rate_limit import RateLimiter
from legal_ai.knowledge.static.db import get_connection

SECRET = "a-test-signing-secret-long-enough-for-hs256"
PASSWORD = "a-sufficiently-long-password"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("LEGAL_AI_JWT_SECRET", SECRET)
    connection = get_connection()
    ensure_account_schema(connection)
    with connection.cursor() as cur:
        cur.execute("DELETE FROM users WHERE email LIKE 'test-%'")
    connection.commit()
    connection.close()
    # A permissive limiter: these tests share one client address and
    # would otherwise trip the login ceiling that protects it.
    yield TestClient(create_app(limiter=RateLimiter(limit=10_000)))
    connection = get_connection()
    with connection.cursor() as cur:
        cur.execute("DELETE FROM users WHERE email LIKE 'test-%'")
    connection.commit()
    connection.close()


def _register(client, email, password=PASSWORD):
    return client.post("/auth/register", json={"email": email, "password": password})


def _login(client, email, password=PASSWORD):
    return client.post("/auth/login", json={"email": email, "password": password})


def test_register_then_login_then_identify(client):
    assert _register(client, "test-flow@example.com").status_code == 200
    token = _login(client, "test-flow@example.com").json()["data"]["access_token"]

    me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["data"]["email"] == "test-flow@example.com"


def test_a_second_registration_of_the_same_email_is_refused(client):
    _register(client, "test-dup@example.com")
    again = _register(client, "test-dup@example.com")
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "email_taken"


def test_a_short_password_is_refused(client):
    response = _register(client, "test-weak@example.com", "short")
    assert response.status_code == 400


def test_an_unknown_email_and_a_wrong_password_answer_identically(client):
    """The enumeration oracle. If these differ by a byte, an attacker can
    ask the service which of a list of addresses hold accounts."""
    _register(client, "test-real@example.com")
    unknown = _login(client, "test-absent@example.com")
    wrong = _login(client, "test-real@example.com", "the-wrong-password-entirely")

    assert unknown.status_code == wrong.status_code == 401
    assert unknown.json() == wrong.json()


def test_research_without_a_token_is_refused(client):
    response = client.post("/research", json={"question": "anything"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "not_authenticated"


def test_research_with_a_forged_token_is_refused(client):
    from api.utils.tokens import issue_access_token

    forged = issue_access_token("someone", secret="a-different-secret-of-sufficient-length")
    response = client.post(
        "/research",
        json={"question": "anything"},
        headers={"Authorization": f"Bearer {forged}"},
    )
    assert response.status_code == 401


def test_research_with_an_expired_token_is_refused(client):
    from api.utils.tokens import issue_access_token

    expired = issue_access_token("someone", secret=SECRET, expires_in=-1)
    response = client.post(
        "/research",
        json={"question": "anything"},
        headers={"Authorization": f"Bearer {expired}"},
    )
    assert response.status_code == 401


def test_a_non_bearer_scheme_is_refused(client):
    _register(client, "test-scheme@example.com")
    token = _login(client, "test-scheme@example.com").json()["data"]["access_token"]
    response = client.get("/auth/me", headers={"Authorization": f"Basic {token}"})
    assert response.status_code == 401


def test_a_token_for_a_deleted_account_is_refused(client):
    """Statelessness has a cost, and this is where it shows: the token is
    validly signed and unexpired, but the account is gone."""
    _register(client, "test-gone@example.com")
    token = _login(client, "test-gone@example.com").json()["data"]["access_token"]

    connection = get_connection()
    with connection.cursor() as cur:
        cur.execute("DELETE FROM users WHERE email = 'test-gone@example.com'")
    connection.commit()
    connection.close()

    response = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


def test_no_configured_secret_closes_the_service(monkeypatch):
    """The failure that must never be an open door: an unset environment
    variable meaning "authentication disabled"."""
    monkeypatch.delenv("LEGAL_AI_JWT_SECRET", raising=False)
    unconfigured = TestClient(create_app(limiter=RateLimiter(limit=10_000)))

    research = unconfigured.post("/research", json={"question": "anything"})
    assert research.status_code == 503
    assert research.json()["error"]["code"] == "auth_unavailable"

    login = unconfigured.post(
        "/auth/login", json={"email": "test-x@example.com", "password": PASSWORD}
    )
    assert login.status_code == 503


def test_health_stays_unauthenticated(client):
    """A liveness probe runs outside any secret the application holds."""
    assert client.get("/health").status_code == 200


def test_no_password_or_hash_is_ever_echoed(client):
    """A response that reflects the credential back is a credential in a
    log, a proxy cache and a browser history."""
    registered = _register(client, "test-echo@example.com")
    logged_in = _login(client, "test-echo@example.com")
    for response in (registered, logged_in):
        assert PASSWORD not in response.text
        assert "argon2" not in response.text
        assert "password_hash" not in response.text
