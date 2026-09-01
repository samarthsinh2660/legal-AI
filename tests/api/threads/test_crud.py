"""Thread CRUD, through the API.

Cross-domain: threads x middleware.

Every case here is really the same question asked twice: does it work, and
does it work only for the owner. A thread holds a user's legal questions, so
"not yours" and "does not exist" answer identically -- telling a caller a
thread exists but is not theirs confirms the id is real.
"""

import pytest
from fastapi.testclient import TestClient

from api.databases.postgres import connection
from api.main import create_app
from api.middleware.rate_limit import RateLimiter
from api.utils.tokens import issue_access_token

SECRET = "a-test-signing-secret-long-enough-for-hs256"
MINE, THEIRS = "test-crud-mine", "test-crud-theirs"


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setenv("LEGAL_AI_JWT_SECRET", SECRET)
    yield create_app(limiter=RateLimiter(limit=10_000))
    with connection() as conn:
        conn.execute("DELETE FROM threads WHERE user_id LIKE 'test-crud-%'")
        conn.commit()


def _client(app, user):
    client = TestClient(app)
    client.headers.update({"Authorization": f"Bearer {issue_access_token(user, secret=SECRET)}"})
    return client


def _new(client, title="New conversation"):
    return client.post("/threads", json={"title": title}).json()["data"]["thread_id"]


def test_create_read_rename_delete(app):
    client = _client(app, MINE)
    thread_id = _new(client, "Refund question")

    assert client.get(f"/threads/{thread_id}").json()["data"]["title"] == "Refund question"

    renamed = client.patch(f"/threads/{thread_id}", json={"title": "Late possession"})
    assert renamed.status_code == 200
    assert renamed.json()["data"]["title"] == "Late possession"

    assert client.delete(f"/threads/{thread_id}").status_code == 200
    assert client.get(f"/threads/{thread_id}").status_code == 404


def test_another_user_cannot_read_it(app):
    thread_id = _new(_client(app, MINE))
    assert _client(app, THEIRS).get(f"/threads/{thread_id}").status_code == 404


def test_another_user_cannot_rename_it(app):
    thread_id = _new(_client(app, MINE), "mine")
    assert _client(app, THEIRS).patch(
        f"/threads/{thread_id}", json={"title": "hijacked"}
    ).status_code == 404
    assert _client(app, MINE).get(f"/threads/{thread_id}").json()["data"]["title"] == "mine"


def test_another_user_cannot_delete_it(app):
    thread_id = _new(_client(app, MINE))
    assert _client(app, THEIRS).delete(f"/threads/{thread_id}").status_code == 404
    assert _client(app, MINE).get(f"/threads/{thread_id}").status_code == 200


def test_another_user_cannot_see_it_listed(app):
    _new(_client(app, MINE))
    assert _client(app, THEIRS).get("/threads").json()["data"]["total"] == 0


def test_deleting_takes_the_messages_with_it(app):
    """ON DELETE CASCADE rather than a second statement, so a half-deleted
    thread is never reachable."""
    client = _client(app, MINE)
    thread_id = _new(client)
    with connection() as conn:
        from api.threads.repository import add_message

        add_message(conn, thread_id, "user", "a question")
    client.delete(f"/threads/{thread_id}")
    with connection() as conn:
        left = conn.execute(
            "SELECT count(*) FROM messages WHERE thread_id = %s", (thread_id,)
        ).fetchone()[0]
    assert left == 0


def test_deleting_twice_is_404_not_an_error(app):
    client = _client(app, MINE)
    thread_id = _new(client)
    assert client.delete(f"/threads/{thread_id}").status_code == 200
    assert client.delete(f"/threads/{thread_id}").status_code == 404


def test_an_empty_title_is_refused(app):
    client = _client(app, MINE)
    thread_id = _new(client)
    assert client.patch(f"/threads/{thread_id}", json={"title": ""}).status_code == 400


def test_renaming_an_unknown_thread_is_404(app):
    assert _client(app, MINE).patch(
        "/threads/no-such-id", json={"title": "x"}
    ).status_code == 404


def test_the_list_is_paged(app):
    client = _client(app, MINE)
    for n in range(5):
        _new(client, f"t{n}")
    page = client.get("/threads?limit=2&offset=0").json()["data"]
    assert len(page["items"]) == 2 and page["total"] == 5 and page["has_more"]
