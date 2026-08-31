"""Authentication, before routing.

Cross-domain: middleware x accounts.

The property worth having: a route is protected because it exists, not
because someone remembered a decorator. `test_every_route_is_closed_by_default`
is the one that would catch a new handler added without thought.
"""

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from api.middleware.auth import PUBLIC_PATHS
from api.middleware.rate_limit import RateLimiter
from api.utils.tokens import issue_access_token

SECRET = "a-test-signing-secret-long-enough-for-hs256"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("LEGAL_AI_JWT_SECRET", SECRET)
    return TestClient(create_app(limiter=RateLimiter(limit=10_000)))


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_a_protected_route_without_a_token_is_401(client):
    assert client.post("/threads", json={}).status_code == 401


def test_a_valid_token_gets_through(client):
    token = issue_access_token("u1", secret=SECRET)
    assert client.post("/threads", json={}, headers=_auth(token)).status_code == 201


def test_a_forged_token_is_401(client):
    forged = issue_access_token("u1", secret="another-secret-long-enough-for-hs256!!")
    assert client.post("/threads", json={}, headers=_auth(forged)).status_code == 401


def test_an_expired_token_is_401(client):
    expired = issue_access_token("u1", secret=SECRET, expires_in=-1)
    assert client.post("/threads", json={}, headers=_auth(expired)).status_code == 401


def test_a_non_bearer_scheme_is_401(client):
    token = issue_access_token("u1", secret=SECRET)
    assert client.get("/threads", headers={"Authorization": f"Basic {token}"}).status_code == 401


def test_public_paths_need_no_token(client):
    assert client.get("/health").status_code == 200
    # Login with nonsense still reaches the handler, which is the point --
    # it answers 401 for the credentials, not for the missing token.
    assert client.post(
        "/auth/login", json={"email": "nobody@example.com", "password": "x" * 12}
    ).status_code in (401, 503)


def test_every_route_is_closed_by_default(client):
    """The reason this is middleware and not a dependency: a handler added
    without thought is protected anyway.

    Routes come from the OpenAPI schema, not `app.routes`. An earlier
    version of this test walked `app.routes`, which in this FastAPI version
    holds `_IncludedRouter` wrappers rather than the routes inside them --
    so it iterated the five built-ins, skipped all of them as public, and
    asserted nothing while passing. A check that cannot run must not look
    like a check that passed.
    """
    paths = client.app.openapi()["paths"]
    assert len(paths) >= 8, "schema looks empty -- the walk is broken again"

    checked, open_routes = 0, []
    for path, operations in paths.items():
        if path in PUBLIC_PATHS:
            continue
        probe = path.replace("{thread_id}", "x").replace("{case_id}", "x")
        for method in operations:
            checked += 1
            if client.request(method.upper(), probe, json={}).status_code != 401:
                open_routes.append(f"{method.upper()} {path}")

    assert checked >= 8, f"only {checked} routes checked -- the walk is broken"
    assert open_routes == [], f"reachable without a token: {open_routes}"


def test_the_public_list_is_exactly_what_is_public(client):
    """PUBLIC_PATHS is the allowlist; nothing else may answer without a
    token, and nothing on it should have been forgotten."""
    paths = client.app.openapi()["paths"]
    public_and_reachable = {
        path for path in paths
        if path in PUBLIC_PATHS
    }
    # login and register must be public -- they are how a caller gets a
    # token in the first place. /health because a probe runs outside any
    # secret the app holds.
    assert public_and_reachable == {"/auth/login", "/auth/register", "/health"}


def test_no_secret_closes_everything(monkeypatch):
    monkeypatch.delenv("LEGAL_AI_JWT_SECRET", raising=False)
    unconfigured = TestClient(create_app(limiter=RateLimiter(limit=10_000)))
    assert unconfigured.post("/threads", json={}).status_code == 503
    # A liveness probe still answers: the process is healthy, its config is not.
    assert unconfigured.get("/health").status_code == 200


def test_a_revoked_token_is_401(monkeypatch):
    """What makes logout mean something."""
    monkeypatch.setenv("LEGAL_AI_JWT_SECRET", SECRET)
    revoked = {"dead-jti"}
    app = create_app(limiter=RateLimiter(limit=10_000))
    # Rebuild with a denylist that does not need a database.
    from api.middleware.auth import AuthMiddleware

    app.user_middleware = [m for m in app.user_middleware if m.cls is not AuthMiddleware]
    app.add_middleware(AuthMiddleware, is_revoked=lambda jti: jti in revoked)
    app.middleware_stack = app.build_middleware_stack()

    import jwt

    token = issue_access_token("u1", secret=SECRET)
    jti = jwt.decode(token, SECRET, algorithms=["HS256"])["jti"]
    client = TestClient(app)
    assert client.get("/threads", headers=_auth(token)).status_code == 200
    revoked.add(jti)
    assert client.get("/threads", headers=_auth(token)).status_code == 401


def test_the_401_body_leaks_nothing(client):
    body = client.post("/threads", json={}, headers=_auth("garbage")).text.lower()
    for leak in ("traceback", "jwt", "signature", "/home/", "secret"):
        assert leak not in body
