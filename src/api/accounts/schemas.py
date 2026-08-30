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


class RegisterResponse(BaseModel):
    user_id: str


class LoginRequest(BaseModel):
    """Credentials.

    Deliberately no length bounds. A rejected-too-short login would tell an
    attacker their guess was the wrong shape before any password check ran,
    which is the enumeration signal the controller works to remove.
    """

    email: str
    password: str


class TokenResponse(BaseModel):
    """A bearer token. Send it as `Authorization: Bearer <access_token>`."""

    access_token: str
    token_type: Literal["bearer"] = "bearer"


class MeResponse(BaseModel):
    user_id: str
    email: str
