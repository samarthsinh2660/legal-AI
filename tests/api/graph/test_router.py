"""The knowledge graph, read-only.

Cross-domain: graph x middleware.

Two properties carry this endpoint. It must be **bounded** -- 48,800 nodes
is not a view, and a landmark judgment with ninety-five citations drawn all
at once says less than a list. And it must be **honest about the bound**:
a graph quietly missing half its edges is a picture that lies about how
connected something is, which is worse than showing nothing.
"""

import pytest
from fastapi.testclient import TestClient

from api.graph.repository import MAX_HOPS, MAX_NODES, neighbourhood
from api.main import create_app
from api.middleware.rate_limit import RateLimiter
from api.utils.tokens import issue_access_token
from legal_ai.graphdb.client import get_driver

SECRET = "a-test-signing-secret-long-enough-for-hs256"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("LEGAL_AI_JWT_SECRET", SECRET)
    c = TestClient(create_app(limiter=RateLimiter(limit=10_000)))
    c.headers.update({"Authorization": f"Bearer {issue_access_token('g1', secret=SECRET)}"})
    return c


@pytest.fixture(scope="module")
def hub():
    """The most-cited judgment: the hardest case for a bounded view."""
    driver = get_driver()
    with driver.session() as s:
        row = s.run(
            "MATCH (a)-[:CITES]->(b:Judgment) RETURN b.document_id AS id, count(a) AS n "
            "ORDER BY n DESC LIMIT 1"
        ).single()
    driver.close()
    return row["id"]


def test_it_returns_nodes_and_edges(client, hub):
    body = client.get(f"/graph/{hub}").json()["data"]
    assert body["nodes"] and body["edges"]
    assert body["nodes"][0]["id"] == hub
    assert body["nodes"][0]["hops"] == 0, "the anchor is the first node"


def test_a_hub_is_capped(client, hub):
    body = client.get(f"/graph/{hub}?limit=20").json()["data"]
    assert len(body["nodes"]) <= 20


def test_a_capped_result_says_so(client, hub):
    """The reader has to know the picture is partial."""
    body = client.get(f"/graph/{hub}?limit=5").json()["data"]
    assert body["truncated"] is True


def test_every_edge_joins_two_returned_nodes(client, hub):
    """An edge to a node the cap removed renders as a line to nowhere."""
    body = client.get(f"/graph/{hub}?limit=30").json()["data"]
    ids = {n["id"] for n in body["nodes"]}
    dangling = [e for e in body["edges"] if e["source"] not in ids or e["target"] not in ids]
    assert dangling == []


def test_nodes_carry_a_kind_so_a_viewer_can_colour_them(client, hub):
    body = client.get(f"/graph/{hub}").json()["data"]
    kinds = {n["kind"] for n in body["nodes"]}
    assert kinds <= {"Judgment", "Section", "Act", "Court"}
    assert kinds, "a node with no label cannot be drawn"


def test_hops_is_capped(client, hub):
    """Three hops from a landmark is a hairball, not a view."""
    assert client.get(f"/graph/{hub}?hops={MAX_HOPS + 1}").status_code == 400


def test_limit_is_capped(client, hub):
    assert client.get(f"/graph/{hub}?limit={MAX_NODES + 1}").status_code == 400


def test_an_unknown_document_is_404(client):
    assert client.get("/graph/no-such-document").status_code == 404


def test_it_needs_a_token(monkeypatch):
    monkeypatch.setenv("LEGAL_AI_JWT_SECRET", SECRET)
    anonymous = TestClient(create_app(limiter=RateLimiter(limit=10_000)))
    assert anonymous.get("/graph/anything").status_code == 401


def test_there_is_no_write_path(client, hub):
    """A reader may look at the graph. Nothing here may change it."""
    for method in ("POST", "PATCH", "DELETE", "PUT"):
        response = client.request(method, f"/graph/{hub}")
        assert response.status_code in (401, 404, 405), f"{method} reached a handler"


def test_a_leaf_is_not_reported_as_truncated():
    """Truncation is asked of the database, not inferred from hitting the
    limit -- otherwise a node with exactly `limit` neighbours lies."""
    driver = get_driver()
    with driver.session() as s:
        row = s.run(
            "MATCH (b:Judgment) WHERE NOT (b)--() RETURN b.document_id AS id LIMIT 1"
        ).single()
    if row is None:
        driver.close()
        pytest.skip("no isolated judgment in the corpus")
    found = neighbourhood(driver, row["id"])
    driver.close()
    assert found.truncated is False and found.edges == []
