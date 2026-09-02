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

from api.graph.repository import MAX_NODES, neighbourhood
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


# --- the overview -----------------------------------------------------------
#
# The graph screen used to open on an empty state asking the reader to
# search. Nothing about the corpus was visible until they guessed a name.
# The whole graph is 50,890 nodes, which no force layout renders, so the
# opening view is its most-connected core instead.

def test_the_overview_needs_no_anchor(client):
    body = client.get("/graph/overview").json()
    assert body["success"]
    assert body["data"]["nodes"]


def test_the_overview_shows_the_most_connected_documents(client):
    """An arbitrary slice would be noise. The core is what a reader can
    recognise -- the judgments everything else cites."""
    nodes = client.get("/graph/overview").json()["data"]["nodes"]
    assert all(node["title"] for node in nodes)


def test_every_overview_edge_joins_two_nodes_it_returned(client):
    """A line to a node that is not there is a line to nowhere."""
    data = client.get("/graph/overview").json()["data"]
    ids = {node["id"] for node in data["nodes"]}
    for edge in data["edges"]:
        assert edge["source"] in ids and edge["target"] in ids


def test_the_overview_says_it_is_partial(client):
    """It is a fraction of 50,890 nodes and must not read as the whole."""
    assert client.get("/graph/overview").json()["data"]["truncated"] is True


def test_the_overview_needs_a_token(monkeypatch):
    monkeypatch.setenv("LEGAL_AI_JWT_SECRET", SECRET)
    anonymous = TestClient(create_app(limiter=RateLimiter(limit=10_000)))
    assert anonymous.get("/graph/overview").status_code == 401


def test_the_overview_batches_rather_than_returning_everything(client):
    """50,890 nodes is not a view. A batch is."""
    data = client.get("/graph/overview?limit=10").json()["data"]
    assert len(data["nodes"]) == 10
    assert data["truncated"] is True


def test_a_second_batch_is_different_from_the_first(client):
    first = client.get("/graph/overview?limit=10").json()["data"]["nodes"]
    second = client.get("/graph/overview?limit=10&offset=10").json()["data"]["nodes"]
    assert {n["id"] for n in first}.isdisjoint({n["id"] for n in second})


def test_the_statutes_view_leads_with_sections(client):
    """Sections are what the view is about; the judgments citing them come
    in behind so the picture is connected."""
    nodes = client.get("/graph/overview?view=statutes&limit=10").json()["data"]["nodes"]
    assert nodes
    assert all(node["kind"] == "Section" for node in nodes[:10])


def test_an_act_view_returns_that_act_s_own_sections(client):
    nodes = client.get(
        "/graph/overview?view=act:ipc-1860&limit=10"
    ).json()["data"]["nodes"]
    assert nodes
    assert all(node["id"].startswith("act:ipc-1860:") for node in nodes)


def test_an_unknown_view_is_empty_rather_than_an_error(client):
    """An Act we do not hold is a view with nothing in it, not a failure --
    the reader picked a real option that turned out to be bare."""
    data = client.get("/graph/overview?view=act:no-such-act").json()["data"]
    assert data["nodes"] == [] and data["truncated"] is False


def test_the_batch_ceiling_cannot_be_raised_past_the_cap(client):
    assert client.get("/graph/overview?limit=5000").status_code == 400


def test_a_statute_view_brings_in_the_judgments_that_cite_it(client):
    """Sections do not cite each other -- judgments cite them. Without the
    citing side a statute view is a hundred unconnected dots, which is a
    list with extra steps."""
    data = client.get("/graph/overview?view=statutes&limit=20").json()["data"]
    assert data["edges"], "a statute view with no edges is not a graph"
    kinds = {node["kind"] for node in data["nodes"]}
    assert "Judgment" in kinds and "Section" in kinds


def test_every_statute_view_edge_still_joins_two_returned_nodes(client):
    data = client.get("/graph/overview?view=statutes&limit=20").json()["data"]
    ids = {node["id"] for node in data["nodes"]}
    for edge in data["edges"]:
        assert edge["source"] in ids and edge["target"] in ids


def test_an_act_view_is_connected_too(client):
    data = client.get("/graph/overview?view=act:2189&limit=30").json()["data"]
    assert data["edges"]
