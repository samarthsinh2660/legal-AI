"""The HTTP surface: auth, health, and the research endpoint.

The one behaviour worth a test more than any other is that the four
verdicts survive the JSON boundary. `DraftAnswer` keeps unsupported,
partially supported and unchecked claims in three separate slots precisely
so a reader can tell them apart; a response model that flattened them into
one "warnings" list would undo the whole verification phase at the last
hop, silently and without failing anything else.

The other is the no-throw convention: the failure paths must produce
`Failure` values, and nothing an exception carried may reach the body.

The graph is faked at `api.research.controller.run_graph` -- one seam, so no
test here needs a model, a network or a database.
"""

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

from api import main as api_main
from api.utils.tokens import issue_access_token
from api.main import create_app
from api.middleware.rate_limit import RateLimiter, reset_ai_quota
from api.utils.errors import Failure, Ok
from legal_ai.schemas.answer import DraftAnswer
from legal_ai.schemas.verification import Claim

KEY = "test-key"

ANSWER = DraftAnswer(
    question="q",
    lede="A lede.",
    key_elements=(Claim(text="supported claim", evidence_ids=("act:1:sec-2",)),),
    applicable_law=("act:1:sec-2",),
    key_judgments=("judgment:9",),
    needs_verification=("evidence is against this",),
    unchecked=("we never looked at this",),
    partially_supported=("true but overstated",),
    support_not_checked=True,
    citations=("act:1:sec-2", "judgment:9"),
)


JWT_SECRET = "a-test-signing-secret-long-enough-for-hs256"


@pytest.fixture
def client(monkeypatch):
    """A client already holding a valid bearer token.

    The token is issued directly rather than through /auth/login: these
    tests are about the research endpoint, and going through a real login
    would make every one of them depend on the users table."""
    monkeypatch.setenv("LEGAL_AI_JWT_SECRET", JWT_SECRET)
    # The per-user AI budget is process-wide; without this the twentieth
    # research test in a run would fail for a reason unrelated to itself.
    reset_ai_quota()
    test_client = TestClient(create_app(limiter=RateLimiter(limit=10_000)))
    token = issue_access_token("test-user", secret=JWT_SECRET)
    test_client.headers.update({"Authorization": f"Bearer {token}"})
    return test_client


def _graph_returns(monkeypatch, state):
    monkeypatch.setattr("api.research.controller.run_graph", lambda inputs: state)


def test_health_needs_no_key(monkeypatch):
    monkeypatch.setattr("api.main.postgres_status", Ok)
    monkeypatch.setattr("api.main.neo4j_status", Ok)
    body = TestClient(create_app(limiter=RateLimiter(limit=10_000))).get("/health").json()
    assert body["data"] == {"status": "ok", "postgres": True, "neo4j": True}


def test_health_reports_a_dead_dependency_without_failing_liveness(monkeypatch):
    monkeypatch.setattr(
        "api.main.postgres_status",
        lambda: Failure(code="postgres_unreachable", message="down", status=503),
    )
    monkeypatch.setattr("api.main.neo4j_status", Ok)
    response = TestClient(create_app(limiter=RateLimiter(limit=10_000))).get("/health")
    assert response.status_code == 200
    assert response.json()["data"] == {
        "status": "degraded",
        "postgres": False,
        "neo4j": True,
    }


def test_an_unreachable_store_is_a_value_not_a_raise(monkeypatch):
    """The probe's whole job is detecting this, so it must not raise -- and
    the connection error it swallowed carries the DSN, hence the password."""

    def refuse():
        raise OSError("connection to server at 'db' (1.2.3.4), port 5433 failed")

    monkeypatch.setattr("api.main.connection", refuse)
    result = api_main.postgres_status()
    assert isinstance(result, Failure)
    assert result.code == "postgres_unreachable"
    assert "1.2.3.4" not in result.message


def test_a_rejected_token_is_a_value_not_a_raise(monkeypatch):
    """The no-throw property, at the auth boundary: a rejection is a
    Failure to be mapped, never an exception unwinding past the route."""
    from api.accounts.controller import current_user_id

    monkeypatch.setenv("LEGAL_AI_JWT_SECRET", JWT_SECRET)
    assert isinstance(current_user_id("Bearer nonsense"), Failure)
    assert current_user_id("Bearer nonsense").status == 401
    good = issue_access_token("someone", secret=JWT_SECRET)
    assert isinstance(current_user_id(f"Bearer {good}"), Ok)


def test_research_without_a_token_is_401(monkeypatch):
    monkeypatch.setenv("LEGAL_AI_JWT_SECRET", JWT_SECRET)
    assert TestClient(create_app(limiter=RateLimiter(limit=10_000))).post("/research", json={"question": "q"}).status_code == 401


def test_an_empty_question_is_400_not_422(client):
    response = client.post(
        "/research", json={"question": "   "}
    )
    assert response.status_code == 400
    assert "message" in response.json()["error"]


def test_an_unknown_verification_level_is_rejected(client):
    response = client.post(
        "/research",
        json={"question": "q", "verification_level": "paranoid"},
    )
    assert response.status_code == 400


def test_the_four_verdicts_stay_apart_in_the_json(client, monkeypatch):
    _graph_returns(monkeypatch, {"draft_answer": ANSWER, "answer": "text"})
    body = client.post(
        "/research", json={"question": "q"}
    ).json()

    assert body["data"]["answer"]["needs_verification"] == ["evidence is against this"]
    assert body["data"]["answer"]["unchecked"] == ["we never looked at this"]
    assert body["data"]["answer"]["partially_supported"] == ["true but overstated"]
    assert body["data"]["answer"]["key_elements"] == [
        {"text": "supported claim", "evidence_ids": ["act:1:sec-2"], "paragraph": None}
    ]
    assert body["data"]["answer"]["support_not_checked"] is True
    assert body["data"]["answer"]["citations"] == ["act:1:sec-2", "judgment:9"]
    assert body["data"]["answer"]["disclaimer"]


def test_the_requested_verification_level_reaches_the_graph(client, monkeypatch):
    seen = {}

    def fake(inputs):
        seen.update(inputs)
        return {"draft_answer": ANSWER, "answer": "text"}

    monkeypatch.setattr("api.research.controller.run_graph", fake)
    client.post(
        "/research",
        json={
            "question": "q",
            "case_id": "case-1",
            "document_ids": ["doc-1"],
            "verification_level": "verified",
        },
    )
    assert seen["verification_level"] == "verified"
    assert seen["case_id"] == "case-1"
    assert seen["document_ids"] == ["doc-1"]


def test_the_default_verification_level_is_the_configured_one(client, monkeypatch):
    """Read from the environment, not from the field defaults: a deployment
    that set LEGAL_AI_VERIFICATION_LEVEL must not be silently downgraded to
    the cheaper mode on every request."""
    seen = {}

    def fake(inputs):
        seen.update(inputs)
        return {"draft_answer": ANSWER, "answer": "text"}

    monkeypatch.setattr("api.research.controller.run_graph", fake)
    client.post("/research", json={"question": "q"})

    from legal_ai.config import Configuration

    assert seen["verification_level"] == Configuration.from_env().verification_level


def test_the_environment_can_raise_the_default_verification_level(client, monkeypatch):
    seen = {}
    monkeypatch.setenv("LEGAL_AI_VERIFICATION_LEVEL", "verified")
    monkeypatch.setattr(
        "api.research.controller.run_graph",
        lambda inputs: seen.update(inputs) or {"draft_answer": ANSWER},
    )
    client.post("/research", json={"question": "q"})
    assert seen["verification_level"] == "verified"


def test_a_halted_clarification_returns_the_question_not_an_empty_answer(
    client, monkeypatch
):
    _graph_returns(monkeypatch, {"clarification_needed": "Which state?"})
    body = client.post(
        "/research", json={"question": "q"}
    ).json()
    assert body["data"]["clarification_needed"] == "Which state?"
    assert body["data"]["answer"] is None


def test_an_internal_failure_leaks_nothing(client, monkeypatch):
    def boom(inputs):
        raise RuntimeError("DSN postgresql://legal_ai:hunter2@db:5433 refused")

    monkeypatch.setattr("api.research.controller.run_graph", boom)
    response = client.post(
        "/research", json={"question": "q"}
    )
    assert response.status_code == 500
    assert response.json() == {
        "success": False,
        "error": {
            "code": "internal_error",
            "message": "Research failed. See server logs.",
        },
    }
    assert "hunter2" not in response.text
    assert "RuntimeError" not in response.text
    assert "Traceback" not in response.text
    assert "legal_ai" not in response.text


def test_a_run_that_outlives_theread_timeout_is_504(client, monkeypatch):
    import time

    monkeypatch.setenv("LEGAL_AI_RESEARCH_TIMEOUT", "0.1")
    monkeypatch.setattr("api.research.controller.run_graph", lambda inputs: time.sleep(2))
    response = client.post(
        "/research", json={"question": "q"}
    )
    assert response.status_code == 504
    assert response.json()["error"]["code"] == "timeout"
