"""Rate limiting: one global limit, plus a per-user limit on AI calls."""

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from api.middleware.rate_limit import (
    DEFAULT_WINDOW_SECONDS,
    RateLimiter,
    check_ai_quota,
    client_key,
    reset_ai_quota,
)


def test_requests_under_the_ceiling_pass():
    limiter = RateLimiter(limit=3)
    assert [limiter.check("caller", now=0) for _ in range(3)] == [None] * 3


def test_the_request_past_the_ceiling_is_refused():
    limiter = RateLimiter(limit=2)
    for _ in range(2):
        limiter.check("caller", now=0)
    assert limiter.check("caller", now=0) is not None


def test_a_refusal_says_how_long_to_wait():
    """A client told only "no" retries immediately."""
    limiter = RateLimiter(limit=1, window=60)
    limiter.check("caller", now=0)
    wait = limiter.check("caller", now=10)
    assert isinstance(wait, int) and 0 < wait <= 60


def test_the_window_reopens():
    limiter = RateLimiter(limit=1, window=60)
    limiter.check("caller", now=0)
    assert limiter.check("caller", now=30) is not None
    assert limiter.check("caller", now=61) is None


def test_two_callers_do_not_share_a_bucket():
    limiter = RateLimiter(limit=1)
    limiter.check("first", now=0)
    assert limiter.check("second", now=0) is None


def test_expired_windows_are_pruned():
    """Without this the map grows per distinct caller forever."""
    limiter = RateLimiter(limit=5, window=60)
    for n in range(10):
        limiter.check(f"caller-{n}", now=0)
    assert limiter.prune(now=DEFAULT_WINDOW_SECONDS + 1) == 10
    assert limiter.prune(now=DEFAULT_WINDOW_SECONDS + 1) == 0


# --- the key ----------------------------------------------------------------

class _Request:
    def __init__(self, host="1.2.3.4", forwarded=None):
        self.client = type("C", (), {"host": host})()
        self.headers = {"x-forwarded-for": forwarded} if forwarded else {}


def test_the_forwarded_header_is_ignored_by_default(monkeypatch):
    """In front of a proxy it is attacker-controlled, and trusting it hands
    every caller unlimited fresh buckets."""
    monkeypatch.delenv("LEGAL_AI_TRUST_PROXY_HEADER", raising=False)
    assert client_key(_Request(forwarded="9.9.9.9")) == "1.2.3.4"


def test_the_forwarded_header_is_used_when_the_deployment_says_so(monkeypatch):
    monkeypatch.setenv("LEGAL_AI_TRUST_PROXY_HEADER", "true")
    assert client_key(_Request(forwarded="9.9.9.9, 10.0.0.1")) == "9.9.9.9"


def test_a_request_with_no_client_still_gets_a_key(monkeypatch):
    monkeypatch.delenv("LEGAL_AI_TRUST_PROXY_HEADER", raising=False)
    request = _Request()
    request.client = None
    assert client_key(request) == "unknown"


# --- per-user AI quota ------------------------------------------------------

def test_a_user_has_their_own_ai_budget():
    reset_ai_quota()
    assert check_ai_quota("user-a") is None
    assert check_ai_quota("user-b") is None


def test_one_user_exhausting_their_budget_does_not_block_another():
    """The reason this is keyed by user and not by address: one account
    behind a shared office address must not spend everyone else's budget."""
    reset_ai_quota()
    from api.middleware.rate_limit import DEFAULT_AI_LIMIT

    for _ in range(DEFAULT_AI_LIMIT + 5):
        check_ai_quota("heavy")
    assert check_ai_quota("heavy") is not None
    assert check_ai_quota("light") is None


# --- through the app --------------------------------------------------------

@pytest.fixture
def strict_client():
    return TestClient(create_app(limiter=RateLimiter(limit=2, window=60)))


def test_the_app_answers_429_past_the_ceiling(strict_client):
    for _ in range(2):
        strict_client.get("/auth/me")
    response = strict_client.get("/auth/me")
    assert response.status_code == 429
    assert response.json()["error"]["code"] == "rate_limited"


def test_the_429_carries_retry_after(strict_client):
    for _ in range(3):
        response = strict_client.get("/auth/me")
    assert int(response.headers["Retry-After"]) > 0


def test_health_is_never_limited(strict_client):
    """A limited liveness probe turns load into a restart loop."""
    for _ in range(20):
        assert strict_client.get("/health").status_code != 429


def test_an_unknown_path_is_counted_too(strict_client):
    """A scanner walking URLs is exactly the traffic worth limiting."""
    for _ in range(2):
        strict_client.get("/no-such-route")
    assert strict_client.get("/no-such-route").status_code == 429


def test_the_error_body_leaks_nothing(strict_client):
    for _ in range(3):
        response = strict_client.get("/auth/me")
    body = response.text.lower()
    for forbidden in ("traceback", "postgres", "psycopg", "secret", "/home/"):
        assert forbidden not in body
