"""The accounts wire contract."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class RegisterRequest(BaseModel):
    """A new account.

    The length floor is repeated in the controller rather than trusted from
    here alone. This bound gives the client a useful 400 naming the field;
    the controller's is the one that actually holds, because it also guards
    every non-HTTP caller.
    """

    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=12, max_length=1024)
    # Optional: the accounts that predate names have none, and a
    # registration that fails on a blank name helps nobody.
    name: str | None = Field(default=None, max_length=80)


class RegisterResponse(BaseModel):
    user_id: str


class RenameRequest(BaseModel):
    """The one editable field. See `controller.rename` for why it is one."""

    name: str = Field(min_length=1, max_length=80)


class ChangeEmailRequest(BaseModel):
    """A new address, and the current password proving it is really them.

    The password is not optional: an address is the account's sign-in handle,
    so a borrowed token must not be able to move it.
    """

    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=1024)


class ProfileResponse(BaseModel):
    user_id: str
    email: str
    name: str | None = None
    created_at: str | None = None


class LoginRequest(BaseModel):
    """Credentials.

    Deliberately no length bounds. A rejected-too-short login would tell an
    attacker their guess was the wrong shape before any password check ran,
    which is the enumeration signal the controller works to remove.
    """

    email: str
    password: str


class TokenResponse(BaseModel):
    """A bearer token, and who it belongs to.

    The identity rides along because the client needs both and asking for
    them separately cost a second round trip on every sign-in. It is also
    what lets a client restore a session on boot without a call at all:
    the token carries its own `exp`, so a stored pair is checkable offline.

    Sent by the same route that just checked the password, so it is the
    server's word on who this is -- not a claim the client decoded.
    """

    access_token: str
    token_type: Literal["bearer"] = "bearer"
    user_id: str
    email: str
    name: str | None = None
