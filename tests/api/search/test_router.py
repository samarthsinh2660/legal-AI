"""Searching the corpus directly.

Cross-domain: search x retrieval x middleware.

The property that matters most is not that it finds things -- retrieval is
tested elsewhere -- but that results here are never dressed as answers.
Nothing has been claimed about a search hit, so there is nothing to verify,
and a client that renders it with an answer's badges is inventing assurance.
"""

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from api.middleware.rate_limit import RateLimiter
from api.utils.tokens import issue_access_token

SECRET = "a-test-signing-secret-long-enough-for-hs256"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("LEGAL_AI_JWT_SECRET", SECRET)
    c = TestClient(create_app(limiter=RateLimiter(limit=10_000)))
    c.headers.update({"Authorization": f"Bearer {issue_access_token('s1', secret=SECRET)}"})
    return c


def test_it_finds_something(client):
    body = client.get("/search?q=dishonour of cheque&limit=5").json()["data"]
    assert body, "the corpus holds NI Act material"
    assert all(item["document_id"] for item in body)


def test_results_carry_no_verification(client):
    """Nothing has been claimed about a search hit. A field here that looked
    like an answer's badge would be assurance the system never gave."""
    body = client.get("/search?q=cheque&limit=3").json()["data"]
    for item in body:
        assert not (set(item) & {"verified", "needs_verification", "unchecked", "claims"})


def test_it_can_be_narrowed_to_statutes(client):
    body = client.get("/search?q=possession&kind=section&limit=5").json()["data"]
    assert body and all(item["kind"] == "section" for item in body)


def test_it_can_be_narrowed_to_judgments(client):
    body = client.get("/search?q=possession&kind=judgment&limit=5").json()["data"]
    assert body and all(item["kind"] == "judgment" for item in body)


def test_an_unknown_kind_is_refused(client):
    assert client.get("/search?q=x&kind=treaty").status_code == 400


def test_a_too_short_query_is_refused(client):
    assert client.get("/search?q=a").status_code == 400


def test_the_limit_is_capped(client):
    from api.search.router import MAX_RESULTS

    assert client.get(f"/search?q=cheque&limit={MAX_RESULTS + 1}").status_code == 400


def test_an_extract_is_bounded(client):
    """A search list showing whole judgments is a download, not a list."""
    body = client.get("/search?q=cheque&limit=5").json()["data"]
    assert all(len(item["extract"]) <= 400 for item in body)


def test_it_needs_a_token(monkeypatch):
    monkeypatch.setenv("LEGAL_AI_JWT_SECRET", SECRET)
    anonymous = TestClient(create_app(limiter=RateLimiter(limit=10_000)))
    assert anonymous.get("/search?q=cheque").status_code == 401


def test_a_search_that_finds_nothing_is_an_empty_list_not_an_error(client):
    body = client.get("/search?q=zzzqqqxxx nonexistent phrase&limit=5")
    assert body.status_code == 200
    assert isinstance(body.json()["data"], list)


def test_a_failed_rewrite_still_searches_the_reader_s_words(client, monkeypatch):
    """The rewrite is a model call. When it fails the search must degrade to
    what it always did, not to nothing."""
    import api.search.router as search_router
    import legal_ai.retrieval.hybrid as hybrid

    seen = {}
    monkeypatch.setattr(
        search_router, "_statutory_phrasing",
        lambda q: (_ for _ in ()).throw(RuntimeError("model down")),
    )

    def fake(query, **kw):
        seen["query"], seen["also"] = query, kw.get("also")
        return []

    monkeypatch.setattr(hybrid, "hybrid_search", fake)
    response = client.get("/search?q=cheque+bounce")

    assert response.status_code == 200
    assert seen["query"] == "cheque bounce"
    assert seen["also"] is None
