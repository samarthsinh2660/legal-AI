"""Cases, scoped to their owner.

`legal_ai.case.store` owns the schema and the reasoning-side reads. This is
the API's own layer over it, and its whole job is the `user_id` filter: the
corpus layer has no idea accounts exist, so ownership is enforced here or
nowhere.

A case with no owner belongs to nobody. Rows created before accounts existed
are unreachable through the API rather than public, which is the safe way
round.
"""

from __future__ import annotations

import uuid

import psycopg

from api.utils.pagination import Page
from legal_ai.case.store import create_case as _create_case


def owns(conn: psycopg.Connection, case_id: str, user_id: str) -> bool:
    return (
        conn.execute(
            "SELECT 1 FROM cases WHERE case_id = %s AND user_id = %s",
            (case_id, user_id),
        ).fetchone()
        is not None
    )


def create(
    conn: psycopg.Connection,
    user_id: str,
    title: str,
    court: str | None = None,
    state: str | None = None,
    case_number: str | None = None,
    parties: tuple[str, ...] = (),
    matter_type: str | None = None,
    status: str | None = None,
    description: str | None = None,
) -> dict:
    """Create a case owned by `user_id`.

    The id is generated here rather than taken from the caller: a
    client-chosen id lets someone probe for, or collide with, another
    firm's matter.
    """
    case_id = uuid.uuid4().hex
    _create_case(
        conn,
        case_id=case_id,
        title=title,
        court=court,
        state=state,
        case_number=case_number,
        parties=parties,
        matter_type=matter_type,
        status=status,
        description=description,
    )
    conn.execute(
        "UPDATE cases SET user_id = %s WHERE case_id = %s", (user_id, case_id)
    )
    conn.commit()
    return get(conn, case_id, user_id)


def get(conn: psycopg.Connection, case_id: str, user_id: str) -> dict | None:
    row = conn.execute(
        "SELECT case_id, title, court, state, case_number, parties, "
        "matter_type, status, description, created_at, updated_at "
        "FROM cases WHERE case_id = %s AND user_id = %s",
        (case_id, user_id),
    ).fetchone()
    if row is None:
        return None
    keys = (
        "case_id", "title", "court", "state", "case_number", "parties",
        "matter_type", "status", "description", "created_at", "updated_at",
    )
    return dict(zip(keys, row))


def listing(conn: psycopg.Connection, user_id: str, limit: int, offset: int) -> Page:
    total = conn.execute(
        "SELECT count(*) FROM cases WHERE user_id = %s", (user_id,)
    ).fetchone()[0]
    rows = conn.execute(
        "SELECT case_id, title, court, state, case_number, parties, "
        "matter_type, status, description, created_at, updated_at "
        "FROM cases WHERE user_id = %s "
        "ORDER BY updated_at DESC LIMIT %s OFFSET %s",
        (user_id, limit, offset),
    ).fetchall()
    keys = (
        "case_id", "title", "court", "state", "case_number", "parties",
        "matter_type", "status", "description", "created_at", "updated_at",
    )
    return Page(
        items=[dict(zip(keys, row)) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


def update(conn: psycopg.Connection, case_id: str, user_id: str, **fields) -> dict | None:
    """Change the named fields. Unset ones are left alone.

    Only the descriptive fields are editable. `case_id`, `user_id` and the
    timestamps are not: renaming a matter is an edit, re-owning one is not.
    """
    allowed = {"title", "court", "state", "case_number",
               "matter_type", "status", "description"}
    changes = {k: v for k, v in fields.items() if k in allowed and v is not None}
    if not changes:
        return get(conn, case_id, user_id)

    assignments = ", ".join(f"{name} = %s" for name in changes)
    row = conn.execute(
        f"UPDATE cases SET {assignments}, updated_at = now() "
        "WHERE case_id = %s AND user_id = %s RETURNING case_id",
        (*changes.values(), case_id, user_id),
    ).fetchone()
    conn.commit()
    return get(conn, case_id, user_id) if row else None


def delete(conn: psycopg.Connection, case_id: str, user_id: str) -> bool:
    """Delete a case, its files, findings and sessions.

    Threads survive: `threads.case_id` is ON DELETE SET NULL, so deleting a
    matter detaches its conversations instead of destroying them. A user
    closing a file has not asked to lose the questions they asked.
    """
    deleted = conn.execute(
        "DELETE FROM cases WHERE case_id = %s AND user_id = %s",
        (case_id, user_id),
    ).rowcount
    conn.commit()
    return deleted > 0


def attach_thread(conn: psycopg.Connection, case_id: str, thread_id: str, user_id: str) -> bool:
    """The design's "Save to case". Both must belong to this user."""
    if not owns(conn, case_id, user_id):
        return False
    updated = conn.execute(
        "UPDATE threads SET case_id = %s WHERE thread_id = %s AND user_id = %s",
        (case_id, thread_id, user_id),
    ).rowcount
    conn.commit()
    return updated > 0
