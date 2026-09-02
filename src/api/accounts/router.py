"""Accounts routes.

The router is the only layer here that speaks HTTP. It reads the request,
hands plain values to the controller, and maps the `Ok`/`Failure` it gets
back onto a status code through `respond`. Nothing below it constructs a
response, so no helper can decide a status from three frames down and no
exception's own text can reach a body.
"""

from __future__ import annotations

from fastapi import APIRouter, Request

from api.accounts.controller import (
    change_email,
    login,
    register,
    rename,
    user_for,
)
from api.accounts.schemas import (
    ChangeEmailRequest,
    LoginRequest,
    ProfileResponse,
    RegisterRequest,
    RegisterResponse,
    RenameRequest,
    TokenResponse,
)
from api.accounts.repository import created_at
from api.databases.postgres import connection
from api.schemas import ErrorResponse, Success
from api.utils.errors import Failure, unauthorized
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
        result = register(conn, request.email, request.password, name=request.name)
    if isinstance(result, Failure):
        return respond(result)
    return success(RegisterResponse(user_id=result.value).model_dump())


@router.post(
    "/login",
    response_model=Success[TokenResponse],
    responses={401: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
)
async def login_for_token(request: LoginRequest):
    """Exchange email and password for a bearer token and the identity.

    Both in one answer. The client needs the identity to render anything,
    and fetching it separately made every sign-in two round trips and
    every page load a third.
    """
    with connection() as conn:
        result = login(conn, request.email, request.password)
    if isinstance(result, Failure):
        return respond(result)
    session = result.value
    return success(
        TokenResponse(
            access_token=session.access_token,
            user_id=session.user_id,
            email=session.email,
            name=session.name,
        ).model_dump()
    )


@router.get(
    "/profile",
    response_model=Success[ProfileResponse],
    responses={401: {"model": ErrorResponse}},
)
async def read_profile(request: Request):
    """The signed-in account, for the profile screen.

    Not a revival of `/auth/me`: nothing calls this on boot, where the
    stored session already answers. It is fetched when a reader opens their
    profile and wants `created_at`, which no token carries.
    """
    with connection() as conn:
        user = user_for(conn, request.state.user_id)
        joined = created_at(conn, request.state.user_id) if user else None
    if user is None:
        return respond(unauthorized())
    return success(
        ProfileResponse(
            user_id=user.user_id, email=user.email,
            name=user.name, created_at=joined,
        ).model_dump()
    )


@router.patch(
    "/profile/email",
    response_model=Success[ProfileResponse],
    responses={
        400: {"model": ErrorResponse},
        401: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
    },
)
async def change_profile_email(request: Request, body: ChangeEmailRequest):
    """Change the sign-in address. Requires the current password.

    Declared before `/profile` so this path is matched as its own route.

    The token keeps working: it carries a user id, not an address. The next
    sign-in uses the new address.
    """
    with connection() as conn:
        result = change_email(conn, request.state.user_id, body.email, body.password)
        joined = created_at(conn, request.state.user_id)
    if isinstance(result, Failure):
        return respond(result)
    user = result.value
    return success(
        ProfileResponse(
            user_id=user.user_id, email=user.email,
            name=user.name, created_at=joined,
        ).model_dump()
    )


@router.patch(
    "/profile",
    response_model=Success[ProfileResponse],
    responses={400: {"model": ErrorResponse}, 401: {"model": ErrorResponse}},
)
async def update_profile(request: Request, body: RenameRequest):
    """Change the display name. The only editable field -- see
    `controller.rename`."""
    with connection() as conn:
        result = rename(conn, request.state.user_id, body.name)
        joined = created_at(conn, request.state.user_id)
    if isinstance(result, Failure):
        return respond(result)
    user = result.value
    return success(
        ProfileResponse(
            user_id=user.user_id, email=user.email,
            name=user.name, created_at=joined,
        ).model_dump()
    )




@router.post("/logout", responses={401: {"model": ErrorResponse}})
async def logout(request: Request):
    """End the session on the client.

    There is no server-side denylist, so this does not invalidate the
    presented token -- a copy of it keeps working until `exp`. What this
    route gives the client is a place to hang the sign-out on, and an
    authenticated 200 telling it the token it just discarded was real.

    Bounding a leaked token is therefore `LEGAL_AI_JWT_EXPIRES_IN`'s job
    alone. Shorten it if that window matters more than staying signed in.

    Idempotent, and requires a valid token like every other route.
    """
    return success({"logged_out": True})
