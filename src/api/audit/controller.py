"""Reading the trail. Returns a value, never a response."""

from __future__ import annotations

from api.audit.repository import count_for, events_for
from api.audit.schemas import AuditEventModel
from api.utils.errors import Ok, Result
from api.utils.pagination import Page


def my_trail(conn, user_id: str, limit: int, offset: int) -> Result:
    """This account's own events, newest first."""
    events = events_for(conn, user_id, limit=limit, offset=offset)
    return Ok(
        Page(
            items=[AuditEventModel(**event.__dict__) for event in events],
            total=count_for(conn, user_id),
            limit=limit,
            offset=offset,
        )
    )
