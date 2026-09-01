"""Case CRUD, and the two design flows.

Cross-domain: cases x threads x middleware.

`design/UX_FLOWS.md` has two entry points and both need an API:

    Flow A  research -> "Save to case"        POST /cases/{id}/threads
    Flow B  create case -> upload -> research POST /cases, then documents

Ownership is the other half of every test here. The corpus layer knows
nothing about accounts, so if the filter is missing at this layer it is
missing everywhere, and two firms on one deployment see each other's matters.
"""

import pytest
from fastapi.testclient import TestClient

from api.databases.postgres import connection
from api.main import create_app
from api.middleware.rate_limit import RateLimiter
from api.utils.tokens import issue_access_token

SECRET = "a-test-signing-secret-long-enough-for-hs256"
MINE, THEIRS = "test-cases-mine", "test-cases-theirs"


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setenv("LEGAL_AI_JWT_SECRET", SECRET)
    yield create_app(limiter=RateLimiter(limit=10_000))
    with connection() as conn:
        conn.execute("DELETE FROM cases WHERE user_id LIKE 'test-cases-%'")
        conn.execute("DELETE FROM threads WHERE user_id LIKE 'test-cases-%'")
        conn.commit()


def _client(app, user):
    client = TestClient(app)
    client.headers.update(
        {"Authorization": f"Bearer {issue_access_token(user, secret=SECRET)}"}
    )
    return client


def _new_case(client, title="Patel v. Shah"):
    return client.post("/cases", json={"title": title}).json()["data"]["case_id"]


def test_create_read_update_delete(app):
    client = _client(app, MINE)
    case_id = _new_case(client)

    assert client.get(f"/cases/{case_id}").json()["data"]["title"] == "Patel v. Shah"

    edited = client.patch(f"/cases/{case_id}", json={"court": "Gujarat High Court"})
    assert edited.status_code == 200
    assert edited.json()["data"]["court"] == "Gujarat High Court"
    assert edited.json()["data"]["title"] == "Patel v. Shah", "PATCH must not clear unnamed fields"

    assert client.delete(f"/cases/{case_id}").status_code == 200
    assert client.get(f"/cases/{case_id}").status_code == 404


def test_another_user_cannot_read_it(app):
    case_id = _new_case(_client(app, MINE))
    assert _client(app, THEIRS).get(f"/cases/{case_id}").status_code == 404


def test_another_user_cannot_edit_it(app):
    case_id = _new_case(_client(app, MINE))
    assert _client(app, THEIRS).patch(
        f"/cases/{case_id}", json={"title": "hijacked"}
    ).status_code == 404


def test_another_user_cannot_delete_it(app):
    case_id = _new_case(_client(app, MINE))
    assert _client(app, THEIRS).delete(f"/cases/{case_id}").status_code == 404
    assert _client(app, MINE).get(f"/cases/{case_id}").status_code == 200


def test_another_user_cannot_see_it_listed(app):
    _new_case(_client(app, MINE))
    assert _client(app, THEIRS).get("/cases").json()["data"]["total"] == 0


def test_the_client_cannot_choose_the_id(app):
    """A caller-supplied id lets someone probe for, or collide with,
    another firm's matter."""
    client = _client(app, MINE)
    first = client.post("/cases", json={"title": "A", "case_id": "chosen-id"})
    assert first.json()["data"]["case_id"] != "chosen-id"


def test_flow_a_attach_a_thread_to_a_case(app):
    """Research first, decide it is a matter afterwards."""
    client = _client(app, MINE)
    thread_id = client.post("/threads", json={}).json()["data"]["thread_id"]
    case_id = _new_case(client)

    assert client.post(
        f"/cases/{case_id}/threads", json={"thread_id": thread_id}
    ).status_code == 200
    assert client.get(f"/threads/{thread_id}").json()["data"]["case_id"] == case_id


def test_attaching_someone_elses_thread_is_refused(app):
    mine, theirs = _client(app, MINE), _client(app, THEIRS)
    their_thread = theirs.post("/threads", json={}).json()["data"]["thread_id"]
    case_id = _new_case(mine)
    assert mine.post(
        f"/cases/{case_id}/threads", json={"thread_id": their_thread}
    ).status_code == 404


def test_attaching_to_someone_elses_case_is_refused(app):
    mine, theirs = _client(app, MINE), _client(app, THEIRS)
    case_id = _new_case(theirs)
    my_thread = mine.post("/threads", json={}).json()["data"]["thread_id"]
    assert mine.post(
        f"/cases/{case_id}/threads", json={"thread_id": my_thread}
    ).status_code == 404


def test_flow_b_create_case_then_upload(app):
    """Create the matter, then put a document in it."""
    client = _client(app, MINE)
    case_id = _new_case(client)
    uploaded = client.post(
        f"/cases/{case_id}/documents",
        files={"file": ("deed.txt", b"The 1998 deed of sale.", "text/plain")},
    )
    assert uploaded.status_code == 201
    listed = client.get(f"/cases/{case_id}/documents").json()["data"]
    assert any(f["filename"] == "deed.txt" for f in listed)


def test_deleting_a_case_detaches_its_threads_rather_than_destroying_them(app):
    """Closing a file is not a request to lose the questions asked in it."""
    client = _client(app, MINE)
    thread_id = client.post("/threads", json={}).json()["data"]["thread_id"]
    case_id = _new_case(client)
    client.post(f"/cases/{case_id}/threads", json={"thread_id": thread_id})

    client.delete(f"/cases/{case_id}")

    survivor = client.get(f"/threads/{thread_id}")
    assert survivor.status_code == 200
    assert survivor.json()["data"]["case_id"] is None


def test_an_empty_title_is_refused(app):
    assert _client(app, MINE).post("/cases", json={"title": ""}).status_code == 400


def test_the_list_is_paged(app):
    client = _client(app, MINE)
    for n in range(5):
        _new_case(client, f"case {n}")
    page = client.get("/cases?limit=2&offset=0").json()["data"]
    assert len(page["items"]) == 2 and page["total"] == 5 and page["has_more"]


def test_the_new_case_form_matches_the_design(app):
    """`design/UX_FLOWS.md` "Creating a case" lists exactly these fields.
    A modal collecting something the API drops is a form that lies."""
    client = _client(app, MINE)
    created = client.post("/cases", json={
        "title": "Patel v. Shah",
        "matter_type": "property",
        "status": "pre-litigation",
        "court": "Gujarat High Court",
        "state": "Gujarat",
        "case_number": "SCA/14562/2022",
        "parties": ["Patel", "Shah"],
        "description": "Adverse possession claim over ancestral land occupied since 1998.",
    })
    assert created.status_code == 201
    data = created.json()["data"]
    assert data["matter_type"] == "property"
    assert data["status"] == "pre-litigation"
    assert "1998" in data["description"]
    assert data["parties"] == ["Patel", "Shah"]


def test_the_description_reaches_the_agents(app):
    """The modal tells the user this seeds every agent. If it stops at the
    database that label is a lie."""
    from legal_ai.case.session import start_session
    from legal_ai.context.serialization import render
    from api.databases.postgres import connection

    client = _client(app, MINE)
    case_id = client.post("/cases", json={
        "title": "Patel v. Shah",
        "description": "Adverse possession over ancestral land occupied since 1998.",
    }).json()["data"]["case_id"]

    with connection() as conn:
        context = start_session(conn, "can I recover possession", case_id=case_id)

    assert context.case_description is not None
    assert "1998" in render(context), "the description never reaches a prompt"


def test_a_case_with_no_description_renders_nothing_extra(app):
    from legal_ai.case.session import start_session
    from legal_ai.context.serialization import render
    from api.databases.postgres import connection

    client = _client(app, MINE)
    case_id = _new_case(client)
    with connection() as conn:
        context = start_session(conn, "a question", case_id=case_id)
    assert context.case_description is None
    assert "The matter:" not in render(context)


def test_the_description_can_be_edited(app):
    client = _client(app, MINE)
    case_id = _new_case(client)
    edited = client.patch(f"/cases/{case_id}", json={"description": "Now with facts."})
    assert edited.json()["data"]["description"] == "Now with facts."


def test_a_thread_cannot_be_created_inside_someone_elses_case(app):
    """Found by review, untested before. `POST /threads` took any case_id:
    naming another firm's matter seeded its description, documents and
    findings into your context -- and wrote your findings back into it."""
    mine, theirs = _client(app, MINE), _client(app, THEIRS)
    their_case = _new_case(theirs)
    refused = mine.post("/threads", json={"case_id": their_case})
    assert refused.status_code == 404


def test_a_thread_can_be_created_inside_my_own_case(app):
    client = _client(app, MINE)
    case_id = _new_case(client)
    created = client.post("/threads", json={"case_id": case_id})
    assert created.status_code == 201
    assert created.json()["data"]["case_id"] == case_id


def test_an_unknown_case_id_is_404_not_a_500(app):
    """It used to reach the foreign key and raise."""
    assert _client(app, MINE).post(
        "/threads", json={"case_id": "no-such-case"}
    ).status_code == 404
