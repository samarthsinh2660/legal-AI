"""Accounts routes.

The router is the only layer here that speaks HTTP. It reads the request,
hands plain values to the controller, and maps the `Ok`/`Failure` it gets
back onto a status code through `respond`. Nothing below it constructs a
response, so no helper can decide a status from three frames down and no
exception's own text can reach a body.
"""

from __future__ import annotations

from fastapi import APIRouter, Request

from api.accounts.controller import login, register, user_for
from api.accounts.revocation import revoke
from api.accounts.schemas import (
    LoginRequest,
    MeResponse,
    RegisterRequest,
    RegisterResponse,
    TokenResponse,
)
from api.databases.postgres import connection
from api.schemas import ErrorResponse, Success
from api.utils.errors import Failure, Result, service_unavailable, unauthorized
from api.utils.response import respond, success

router = APIRouter(prefix="/auth", tags=["accounts"])


@router.post(
    "/register",
    response_model=Success[RegisterResponse],
    responses={400: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
)
async def register_account(request: RegisterRequest):
    """Create an account.

    Open to anyone who can reach the service, which is a deployment
    decision and not a settled one -- see docs/API.md Limits.
    """
    with connection() as conn:
        result = register(conn, request.email, request.password)
    if isinstance(result, Failure):
        return respond(result)
    return success(RegisterResponse(user_id=result.value).model_dump())


@router.post(
    "/login",
    response_model=Success[TokenResponse],
    responses={401: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
)
async def login_for_token(request: LoginRequest):
    """Exchange email and password for a bearer token."""
    with connection() as conn:
        result = login(conn, request.email, request.password)
    if isinstance(result, Failure):
        return respond(result)
    return success(TokenResponse(access_token=result.value).model_dump())


@router.get(
    "/me",
    response_model=Success[MeResponse],
    responses={401: {"model": ErrorResponse}},
)
async def me(request: Request):
    """Who the presented token belongs to.

    The endpoint a client uses to tell a live session from an expired one
    without spending a research call to find out.
    """
    with connection() as conn:
        user = user_for(conn, request.state.user_id)
    if user is None:
        # A validly signed token for an account that no longer exists. The
        # same answer as any other bad token: the difference is useful to
        # an attacker and to nobody else.
        return respond(unauthorized())
    return success(MeResponse(user_id=user.user_id, email=user.email).model_dump())


@router.post("/logout", responses={401: {"model": ErrorResponse}})
async def logout(request: Request):
    """Invalidate the presented token.

    A real revocation, not a note to the client. The token is signed and
    unexpired, so anyone holding a copy could keep using it; writing its
    `jti` to the denylist is what makes logging out mean something.

    Idempotent -- logging out twice is not an error.

    The `jti` comes from `request.state`, where AuthMiddleware put it after
    verifying the signature. Re-decoding here would either repeat that work
    or, worse, read an unverified token.
    """
    with connection() as conn:
        revoked = revoke(conn, request.state.jti, request.state.token_expires_at)
    if not revoked:
        # Issued before tokens carried an id. It stays valid until it
        # expires, and saying otherwise would be the lie.
        return respond(
            service_unavailable(
                "logout_unavailable",
                "This session cannot be ended early; it expires on its own.",
            )
        )
    return success({"logged_out": True})
