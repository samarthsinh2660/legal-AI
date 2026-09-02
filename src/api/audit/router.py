"""Reading the audit trail.

Only your own events. There is no firm-administrator role yet, so there is
no route that reads another user's trail -- adding one before the role
exists would be an access-control hole dressed as a feature.

Read-only by design: no route creates, edits or removes an event, because
an audit trail that can be rewritten is not one. Events are written by
`middleware.audit`, where a route cannot forget to.
"""

from __future__ import annotations

from fastapi import APIRouter, Query, Request

from api.audit.controller import my_trail as read_trail
from api.audit.schemas import AuditEventModel
from api.databases.postgres import connection
from api.schemas import Success
from api.utils.pagination import MAX_LIMIT, PageParams, PageResponse
from api.utils.response import success

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("", response_model=Success[PageResponse[AuditEventModel]])
async def my_trail(
    request: Request,
    # Must match PageParams' own ceiling: a value between the two would
    # pass here and raise inside the handler, outside the envelope.
    limit: int = Query(default=50, ge=1, le=MAX_LIMIT),
    offset: int = Query(default=0, ge=0),
):
    """What this account has done, newest first."""
    params = PageParams(limit=limit, offset=offset)
    with connection() as conn:
        result = read_trail(
            conn, request.state.user_id, params.limit, params.offset
        )
    return success(PageResponse.of(result.value).model_dump())
