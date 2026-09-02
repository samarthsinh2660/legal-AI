"""Who did what, to which matter, and when.

A firm will not put client data in a tool it cannot audit, and that is the
first thing asked for -- ahead of features. This is the only layer that
writes the table.

What is recorded is narrow on purpose: the actor, the action, the resource
and the outcome. Never the question, the answer or a document's text. All
of that is already stored once under the user's own row, and a second copy
here would be a second place for privileged material to leak from, with a
different retention policy and a different set of eyes on it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import psycopg


@dataclass(frozen=True)
class AuditEvent:
    event_id: int
    user_id: str
    action: str
    resource_type: str
    resource_id: str | None
    status: int
    at: datetime


def ensure_audit_schema(conn: psycopg.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS audit_events (
            event_id      BIGSERIAL PRIMARY KEY,
            user_id       TEXT NOT NULL,
            action        TEXT NOT NULL,
            resource_type TEXT NOT NULL,
            resource_id   TEXT,
            status        INT NOT NULL,
            at            TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    # The question the table exists to answer is "what did this user touch,
    # most recently first".
    conn.execute(
        "CREATE INDEX IF NOT EXISTS audit_events_user_idx "
        "ON audit_events (user_id, event_id DESC)"
    )
    # And its mirror: "who touched this matter".
    conn.execute(
        "CREATE INDEX IF NOT EXISTS audit_events_resource_idx "
        "ON audit_events (resource_type, resource_id, event_id DESC)"
    )
    conn.commit()


def record(
    conn: psycopg.Connection,
    user_id: str,
    action: str,
    resource_type: str,
    resource_id: str | None,
    status: int,
) -> None:
    """Append one event. Never updates and never deletes -- an audit trail
    that can be edited is not one."""
    conn.execute(
        "INSERT INTO audit_events "
        "(user_id, action, resource_type, resource_id, status) "
        "VALUES (%s, %s, %s, %s, %s)",
        (user_id, action, resource_type, resource_id, status),
    )
    conn.commit()


def count_for(conn: psycopg.Connection, user_id: str) -> int:
    """How many events this user has, for paging."""
    return conn.execute(
        "SELECT count(*) FROM audit_events WHERE user_id = %s", (user_id,)
    ).fetchone()[0]


def events_for(
    conn: psycopg.Connection, user_id: str, limit: int = 100, offset: int = 0
) -> list[AuditEvent]:
    """This user's own events, newest first.

    Scoped by `user_id` in the WHERE clause like every other query here: one
    firm's trail is client data about client data.
    """
    rows = conn.execute(
        "SELECT event_id, user_id, action, resource_type, resource_id, status, at "
        "FROM audit_events WHERE user_id = %s "
        "ORDER BY event_id DESC LIMIT %s OFFSET %s",
        (user_id, limit, offset),
    ).fetchall()
    return [AuditEvent(*row) for row in rows]
