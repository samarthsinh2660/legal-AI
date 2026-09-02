"""Record every authenticated request that touches client data.

In middleware rather than in each route for the same reason authorisation
is: a route that forgets to record leaves a hole nobody sees. Here it
cannot be forgotten.

Runs INSIDE AuthMiddleware, so `request.state.user_id` is already set and
an unauthenticated request is never attributed to anyone.
"""

from __future__ import annotations

import asyncio
import logging

from starlette.middleware.base import BaseHTTPMiddleware

from api.audit.repository import record
from api.databases.postgres import connection

log = logging.getLogger(__name__)

# Path prefix -> what a firm would call it. `/health` and the docs are
# absent deliberately: a liveness probe every ten seconds would bury the
# rows that matter.
#
# `/auth` is absent too. Sign-ins are recorded in the accounts controller,
# which is the only place that knows whose they are, and the remaining
# account routes have no resource id -- recording "me" or "logout" as one
# would fill the resource index with path segments.
_RESOURCES = (
    ("/threads", "thread"),
    ("/cases", "case"),
    ("/search", "search"),
    ("/graph", "graph"),
    ("/audit", "audit"),
)

_ACTIONS = {
    "GET": "read",
    "POST": "create",
    "PATCH": "update",
    "DELETE": "delete",
}


def _describe(path: str, method: str) -> tuple[str, str | None] | None:
    """`(resource_type, resource_id)` for a path, or None to skip it."""
    for prefix, resource_type in _RESOURCES:
        if path == prefix or path.startswith(prefix + "/"):
            rest = path[len(prefix):].strip("/").split("/")
            # The id is the first segment after the collection, when there
            # is one: /cases/abc/documents -> "abc". A document belongs to
            # its case and is indexed under it, because the question this
            # index answers is "who touched this matter".
            resource_id = rest[0] if rest and rest[0] else None
            return resource_type, resource_id
    return None


class AuditMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        try:
            response = await call_next(request)
        except Exception:
            # A handler that raised still touched the matter. Recording it
            # as a 500 is the difference between a trail with a hole and a
            # trail that says what happened.
            await self._record(request, 500)
            raise

        await self._record(request, response.status_code)
        return response

    async def _record(self, request, status: int) -> None:
        user_id = getattr(request.state, "user_id", None)
        described = _describe(request.url.path, request.method)
        if not user_id or described is None or request.method == "OPTIONS":
            return

        resource_type, resource_id = described
        action = _ACTIONS.get(request.method, request.method.lower())

        def write() -> None:
            with connection() as conn:
                record(conn, user_id, action, resource_type, resource_id, status)

        try:
            # Off the event loop. The pool is small and a streamed research
            # turn holds a connection for minutes, so a blocking borrow here
            # would stall every other request -- including the ones whose
            # completion would release the connection this one is waiting on.
            await asyncio.to_thread(write)
        except Exception:
            # The trail must not become a single point of failure for the
            # service: a firm losing access to its own matters because an
            # audit insert failed is worse than a gap. The gap is loud
            # instead, and a silent one would be the real defect.
            log.error(
                "audit: could not record %s %s for user %s",
                request.method, request.url.path, user_id, exc_info=True,
            )
