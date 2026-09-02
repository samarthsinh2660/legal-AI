"""The display name: stored at registration, shown instead of the address,
editable afterwards.

The name is the only editable field. Changing an address re-keys the
account and wants a confirmation round trip; changing a password wants the
old one. Both are absent rather than half-built, and these tests hold that.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from api.middleware.rate_limit import RateLimiter

PASSWORD = "correct-horse-battery"


@pytest.fixture
def client():
    return TestClient(create_app(limiter=RateLimiter(limit=10_000)))


def _account(client, name=None):
    email = f"profile-{uuid.uuid4().hex[:10]}@example.com"
    body = {"email": email, "password": PASSWORD}
    if name is not None:
        body["name"] = name
    assert client.post("/auth/register", json=body).status_code == 200
    token = client.post(
        "/auth/login", json={"email": email, "password": PASSWORD}
    ).json()["data"]
    return email, token


def test_a_name_given_at_registration_comes_back_with_the_token(client):
    """The sidebar shows it, so login must carry it -- otherwise the first
    render after signing in has only the address to show."""
    _, session = _account(client, name="Samarth Sinh")
    assert session["name"] == "Samarth Sinh"


def test_an_account_registered_without_a_name_has_none(client):
    """Not the address, and not a guess derived from it: a name nobody
    entered would be a fabrication in the one place a reader trusts."""
    _, session = _account(client)
    assert session["name"] is None


def test_the_profile_carries_when_the_account_was_made(client):
    """The reason this endpoint exists at all -- no token carries it."""
    email, session = _account(client, name="A Reader")
    auth = {"Authorization": f"Bearer {session['access_token']}"}

    body = client.get("/auth/profile", headers=auth).json()["data"]
    assert body["email"] == email
    assert body["name"] == "A Reader"
    assert body["created_at"]


def test_a_name_can_be_changed(client):
    _, session = _account(client, name="Old Name")
    auth = {"Authorization": f"Bearer {session['access_token']}"}

    patched = client.patch("/auth/profile", json={"name": "New Name"}, headers=auth)
    assert patched.status_code == 200
    assert patched.json()["data"]["name"] == "New Name"
    # Re-read, so the assertion is about what was stored rather than what
    # the write happened to echo back.
    assert client.get("/auth/profile", headers=auth).json()["data"]["name"] == "New Name"


def test_a_blank_name_is_refused(client):
    """Saving an empty box would silently drop the name the user had."""
    _, session = _account(client, name="Keep Me")
    auth = {"Authorization": f"Bearer {session['access_token']}"}

    assert client.patch("/auth/profile", json={"name": "   "}, headers=auth).status_code == 400
    assert client.get("/auth/profile", headers=auth).json()["data"]["name"] == "Keep Me"


def test_the_profile_needs_a_token(client):
    assert client.get("/auth/profile").status_code == 401
    assert client.patch("/auth/profile", json={"name": "x"}).status_code == 401


def test_one_account_cannot_rename_another(client):
    """The id comes from the token, never from the body -- otherwise a
    caller could pass someone else's."""
    _, first = _account(client, name="First")
    _, second = _account(client, name="Second")

    client.patch(
        "/auth/profile",
        json={"name": "Hijacked", "user_id": first["user_id"]},
        headers={"Authorization": f"Bearer {second['access_token']}"},
    )
    assert client.get(
        "/auth/profile", headers={"Authorization": f"Bearer {first['access_token']}"}
    ).json()["data"]["name"] == "First"


def test_the_email_can_be_changed_with_the_password(client):
    email, session = _account(client, name="Mover")
    auth = {"Authorization": f"Bearer {session['access_token']}"}
    fresh = f"moved-{uuid.uuid4().hex[:8]}@example.com"

    changed = client.patch(
        "/auth/profile/email",
        json={"email": fresh, "password": PASSWORD},
        headers=auth,
    )
    assert changed.status_code == 200
    assert changed.json()["data"]["email"] == fresh

    # The new address signs in; the old one no longer does.
    assert client.post(
        "/auth/login", json={"email": fresh, "password": PASSWORD}
    ).status_code == 200
    assert client.post(
        "/auth/login", json={"email": email, "password": PASSWORD}
    ).status_code == 401


def test_the_existing_token_keeps_working_after_an_email_change(client):
    """It carries a user id, not an address. Signing someone out of every
    device for changing their own email would be a worse product."""
    _, session = _account(client)
    auth = {"Authorization": f"Bearer {session['access_token']}"}
    client.patch(
        "/auth/profile/email",
        json={"email": f"kept-{uuid.uuid4().hex[:8]}@example.com", "password": PASSWORD},
        headers=auth,
    )
    assert client.get("/auth/profile", headers=auth).status_code == 200


def test_a_wrong_password_cannot_move_the_address(client):
    """A token alone must not be enough: the address is the sign-in handle,
    so a borrowed session could otherwise take the account."""
    email, session = _account(client)
    auth = {"Authorization": f"Bearer {session['access_token']}"}

    refused = client.patch(
        "/auth/profile/email",
        json={"email": "attacker@example.com", "password": "not-the-password"},
        headers=auth,
    )
    assert refused.status_code == 400
    assert client.get("/auth/profile", headers=auth).json()["data"]["email"] == email


def test_an_address_already_taken_is_refused(client):
    first, _ = _account(client)
    _, second = _account(client)

    clash = client.patch(
        "/auth/profile/email",
        json={"email": first, "password": PASSWORD},
        headers={"Authorization": f"Bearer {second['access_token']}"},
    )
    assert clash.status_code == 409
    assert clash.json()["error"]["code"] == "email_taken"


def test_a_malformed_address_is_refused(client):
    _, session = _account(client)
    auth = {"Authorization": f"Bearer {session['access_token']}"}
    assert client.patch(
        "/auth/profile/email", json={"email": "not-an-email", "password": PASSWORD},
        headers=auth,
    ).status_code == 400


def test_changing_the_email_needs_a_token(client):
    assert client.patch(
        "/auth/profile/email", json={"email": "x@y.com", "password": PASSWORD}
    ).status_code == 401
