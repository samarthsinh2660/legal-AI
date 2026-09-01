"""Authentication, before routing.

Every request is checked here rather than by a dependency on each route.
With `Depends`, a route is protected because somebody remembered; a new
handler added on a Friday is public until someone notices. Here the default
is closed and the exceptions are a list you have to edit on purpose.

The verified user id goes on `request.state.user_id`, so a handler reads who
is asking instead of re-parsing a header.

Public paths are enumerated below and nowhere else. `/health` because a
liveness probe runs outside any secret the app holds, login and register
because they are how a caller gets a token, and the docs because they
describe the API rather than serve it.
"""

from __future__ import annotations

import asyncio
import os

from starlette.middleware.base import BaseHTTPMiddleware

from api.utils.errors import service_unavailable, unauthorized
from api.utils.response import respond
from api.utils.tokens import TokenError, read_claims

PUBLIC_PATHS = frozenset({
    "/health",
    "/auth/login",
    "/auth/register",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/docs/oauth2-redirect",
})


class AuthMiddleware(BaseHTTPMiddleware):
    """Rejects any request without a usable token, except on PUBLIC_PATHS."""

    def __init__(self, app, is_revoked=None):
        super().__init__(app)
        # Injected so the check can be tested without a database, and so a
        # deployment could swap the store without touching this file.
        self._is_revoked = is_revoked

    async def dispatch(self, request, call_next):
        # A browser sends a preflight without credentials, so requiring a
        # token here breaks every cross-origin call -- including when CORS
        # is unconfigured and CORSMiddleware is not mounted to catch it.
        if request.method == "OPTIONS" or request.url.path in PUBLIC_PATHS:
            return await call_next(request)

        secret = os.environ.get("LEGAL_AI_JWT_SECRET", "")
        if not secret:
            # An unset secret closes the service. The other default turns
            # one missing variable into an open endpoint.
            return respond(
                service_unavailable(
                    "auth_unavailable",
                    "Authentication is not configured on this server.",
                )
            )

        scheme, _, token = (request.headers.get("authorization") or "").partition(" ")
        if scheme.lower() != "bearer" or not token:
            return respond(unauthorized())

        try:
            claims = read_claims(token, secret=secret)
        except TokenError:
            # Expired, forged, unsigned and malformed answer the same.
            return respond(unauthorized())

        if self._is_revoked is not None:
            # Off the event loop: the check is a database round trip, and
            # doing it inline stalls every other in-flight request for its
            # duration -- badly so when the pool is busy.
            revoked = await asyncio.to_thread(self._is_revoked, claims.get("jti", ""))
            if revoked:
                return respond(unauthorized())

        request.state.user_id = claims["sub"]
        # Carried so logout can revoke this exact token without decoding it
        # a second time.
        request.state.jti = claims.get("jti", "")
        request.state.token_expires_at = int(claims.get("exp", 0))
        return await call_next(request)
