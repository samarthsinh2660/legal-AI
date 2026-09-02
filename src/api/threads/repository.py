"""Threads and messages -- the only place that reads or writes them.

Every query takes a `user_id` and puts it in the WHERE clause. Filtering
after the read is one forgotten call away from serving another firm's
thread, so the scoping is in the SQL rather than around it.

An assistant message keeps its structured answer alongside its text: a later
turn cites what was established rather than re-deriving it, and that needs
the claims, not the prose.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import psycopg

from api.utils.pagination import Page


# One spelling, used by the column default, the router and both send paths.
# They disagreed once -- "New thread" against "New conversation" -- and the
# auto-title silently never fired on the non-streaming path.
DEFAULT_TITLE = "New conversation"


@dataclass(frozen=True)
class Thread:
    thread_id: str
    user_id: str
    title: str
    case_id: str | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class Message:
    message_id: int
    thread_id: str
    role: str
    content: str
    answer: dict[str, Any] | None
    created_at: datetime


def ensure_thread_schema(conn: psycopg.Connection) -> None:
    """Create the chat tables if absent. Idempotent."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS threads (
            thread_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            case_id TEXT REFERENCES cases(case_id) ON DELETE SET NULL,
            title TEXT NOT NULL DEFAULT 'New thread',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS messages (
            message_id BIGSERIAL PRIMARY KEY,
            thread_id TEXT NOT NULL
                REFERENCES threads(thread_id) ON DELETE CASCADE,
            role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
            content TEXT NOT NULL,
            answer JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    # The thread list is "my threads, most recent first".
    conn.execute(
        "CREATE INDEX IF NOT EXISTS threads_user_idx "
        "ON threads (user_id, updated_at DESC)"
    )
    # Reading a thread is always in order, and message_id breaks ties
    # between rows written inside the same clock tick.
    conn.execute(
        "CREATE INDEX IF NOT EXISTS messages_thread_idx "
        "ON messages (thread_id, message_id)"
    )
    conn.commit()


def create_thread(
    conn: psycopg.Connection,
    user_id: str,
    title: str = DEFAULT_TITLE,
    case_id: str | None = None,
) -> Thread:
    thread_id = uuid.uuid4().hex
    row = conn.execute(
        """
        INSERT INTO threads (thread_id, user_id, title, case_id)
        VALUES (%s, %s, %s, %s)
        RETURNING thread_id, user_id, title, case_id, created_at, updated_at
        """,
        (thread_id, user_id, title, case_id),
    ).fetchone()
    conn.commit()
    return Thread(*row)


def get_thread(
    conn: psycopg.Connection, thread_id: str, user_id: str
) -> Thread | None:
    """One thread, or None if it is missing *or* not this user's.

    The two are deliberately indistinguishable: telling a caller a
    thread exists but is not theirs confirms the id is real.
    """
    row = conn.execute(
        "SELECT thread_id, user_id, title, case_id, created_at, updated_at "
        "FROM threads WHERE thread_id = %s AND user_id = %s",
        (thread_id, user_id),
    ).fetchone()
    return Thread(*row) if row else None


def list_threads(
    conn: psycopg.Connection, user_id: str, limit: int, offset: int
) -> Page:
    total = conn.execute(
        "SELECT count(*) FROM threads WHERE user_id = %s", (user_id,)
    ).fetchone()[0]
    rows = conn.execute(
        "SELECT thread_id, user_id, title, case_id, created_at, updated_at "
        "FROM threads WHERE user_id = %s "
        "ORDER BY updated_at DESC LIMIT %s OFFSET %s",
        (user_id, limit, offset),
    ).fetchall()
    return Page(
        items=[Thread(*row) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


def add_message(
    conn: psycopg.Connection,
    thread_id: str,
    role: str,
    content: str,
    answer: dict[str, Any] | None = None,
    user_id: str | None = None,
) -> Message | None:
    """Append a message, and move its thread to the top of the list.

    `user_id` is optional so an internal caller that has already checked
    ownership need not re-state it. When given, the insert is refused unless
    the thread belongs to that user -- None back, nothing written.
    """
    if user_id is not None:
        owner = conn.execute(
            "SELECT 1 FROM threads WHERE thread_id = %s AND user_id = %s",
            (thread_id, user_id),
        ).fetchone()
        if owner is None:
            return None

    row = conn.execute(
        """
        INSERT INTO messages (thread_id, role, content, answer)
        VALUES (%s, %s, %s, %s)
        RETURNING message_id, thread_id, role, content, answer, created_at
        """,
        (thread_id, role, content, json.dumps(answer) if answer else None),
    ).fetchone()
    conn.execute(
        "UPDATE threads SET updated_at = now() WHERE thread_id = %s",
        (thread_id,),
    )
    conn.commit()
    return Message(*row)


def list_messages(
    conn: psycopg.Connection, thread_id: str, user_id: str
) -> list[Message]:
    """Every message in the thread, oldest first. Empty if not this user's.

    The join on user_id is what enforces ownership: without it a caller
    holding any thread id could read any thread.
    """
    rows = conn.execute(
        """
        SELECT m.message_id, m.thread_id, m.role, m.content, m.answer, m.created_at
        FROM messages m
        JOIN threads c USING (thread_id)
        WHERE m.thread_id = %s AND c.user_id = %s
        ORDER BY m.message_id
        """,
        (thread_id, user_id),
    ).fetchall()
    return [Message(*row) for row in rows]


def recent_answers(
    conn: psycopg.Connection, thread_id: str, user_id: str, limit: int
) -> list[dict[str, Any]]:
    """The structured answers of the last `limit` assistant turns, oldest first.

    The counterpart to `recent_turns`, which drops `answer` because prose is
    all the rewriter and the router need. Composing a reply out of what the
    thread established needs the opposite: the claims and their buckets, not
    the paragraph they were rendered into. Turns that stored no structured
    answer are absent rather than present-and-empty -- there is nothing in
    them to carry forward.
    """
    rows = conn.execute(
        """
        SELECT m.answer
        FROM messages m
        JOIN threads t USING (thread_id)
        WHERE m.thread_id = %s AND t.user_id = %s
          AND m.role = 'assistant' AND m.answer IS NOT NULL
        ORDER BY m.message_id DESC
        LIMIT %s
        """,
        (thread_id, user_id, limit),
    ).fetchall()
    return [row[0] for row in reversed(rows) if isinstance(row[0], dict)]


def set_title(conn: psycopg.Connection, thread_id: str, user_id: str, title: str) -> None:
    """Name the thread from its first message, so a sidebar is readable."""
    conn.execute(
        "UPDATE threads SET title = %s "
        "WHERE thread_id = %s AND user_id = %s",
        (title, thread_id, user_id),
    )
    conn.commit()


def rename_thread(
    conn: psycopg.Connection, thread_id: str, user_id: str, title: str
) -> Thread | None:
    """Rename, or None if it is missing or not this user's."""
    row = conn.execute(
        "UPDATE threads SET title = %s, updated_at = now() "
        "WHERE thread_id = %s AND user_id = %s "
        "RETURNING thread_id, user_id, title, case_id, created_at, updated_at",
        (title, thread_id, user_id),
    ).fetchone()
    conn.commit()
    return Thread(*row) if row else None


def delete_thread(conn: psycopg.Connection, thread_id: str, user_id: str) -> bool:
    """Delete the thread and its messages. False if it was not this user's.

    Messages go with it through ON DELETE CASCADE rather than a second
    statement, so a half-deleted thread is not reachable.
    """
    deleted = conn.execute(
        "DELETE FROM threads WHERE thread_id = %s AND user_id = %s",
        (thread_id, user_id),
    ).rowcount
    conn.commit()
    return deleted > 0


def recent_turns(
    conn: psycopg.Connection, thread_id: str, user_id: str, limit: int
) -> list[Message]:
    """The last `limit` messages, oldest first.

    Bounded in SQL, and without `answer`. Reading the whole thread to keep
    the tail transfers every stored answer's JSONB on every turn -- megabytes
    on a long thread, 96% of it discarded in Python.
    """
    rows = conn.execute(
        """
        SELECT m.message_id, m.thread_id, m.role, m.content, m.created_at
        FROM messages m
        JOIN threads t USING (thread_id)
        WHERE m.thread_id = %s AND t.user_id = %s
        ORDER BY m.message_id DESC
        LIMIT %s
        """,
        (thread_id, user_id, limit),
    ).fetchall()
    return [
        Message(row[0], row[1], row[2], row[3], None, row[4])
        for row in reversed(rows)
    ]
