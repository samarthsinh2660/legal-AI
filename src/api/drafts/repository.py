"""Drafted documents, scoped to the thread they came out of.

A draft is a row, not a file on disk. The bytes live in the row because a
notice is tens of kilobytes and losing the filesystem must not lose the
document; and because a draft belongs to a thread, so the thread's own
ownership check is the only one that has to be right.

`status` exists for the same reason the thread's answers poll: a document
takes a model call and a render, and the reader who clicked the button
needs to see something true while it happens. It is the honest version of
the run status the queue will one day carry -- see
docs/RELIABILITY_ARCHITECTURE.md.
"""

from __future__ import annotations

import uuid

import psycopg

from api.utils.pagination import Page

# What a draft can be. `failed` carries its reason in `error`, because a
# draft that could not be produced must say why rather than vanish.
STATUSES = ("running", "done", "failed")


def ensure_draft_schema(conn: psycopg.Connection) -> None:
    """Create the drafts table if absent. Idempotent."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS drafts (
            draft_id TEXT PRIMARY KEY,
            thread_id TEXT NOT NULL
                REFERENCES threads(thread_id) ON DELETE CASCADE,
            document_type TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('running', 'done', 'failed')),
            filename TEXT NOT NULL DEFAULT '',
            -- The model's structure, kept beside the file so a document can
            -- be re-rendered when the template changes without paying for
            -- the model again.
            structure JSONB,
            docx BYTEA,
            error TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            finished_at TIMESTAMPTZ
        )
        """
    )
    # "The drafts on this thread, in the order they were asked for" is the
    # only listing there is.
    conn.execute(
        "CREATE INDEX IF NOT EXISTS drafts_thread_idx "
        "ON drafts (thread_id, created_at)"
    )
    conn.commit()


def start(conn: psycopg.Connection, thread_id: str, document_type: str) -> str:
    """Record a draft as running and return its id.

    Written before the model is called, so a reader who reloads mid-run
    sees a document being prepared rather than nothing at all.
    """
    draft_id = uuid.uuid4().hex
    conn.execute(
        "INSERT INTO drafts (draft_id, thread_id, document_type, status) "
        "VALUES (%s, %s, %s, 'running')",
        (draft_id, thread_id, document_type),
    )
    conn.commit()
    return draft_id


def finish(
    conn: psycopg.Connection,
    draft_id: str,
    filename: str,
    structure: dict,
    docx: bytes,
) -> None:
    """Store the finished document. The status moves only here."""
    from psycopg.types.json import Json

    conn.execute(
        "UPDATE drafts SET status = 'done', filename = %s, structure = %s, "
        "docx = %s, finished_at = now() WHERE draft_id = %s",
        (filename, Json(structure), docx, draft_id),
    )
    conn.commit()


# Validator language, and what it means to the person who clicked. The
# checks are written for the drafter; "rests on no provision" reached a
# reader on 2026-09-05 and told them nothing they could act on.
_IN_PLAIN_WORDS = {
    "rests on no provision": (
        "The conversation did not establish law this document could be built on."
    ),
    "states no facts": "The conversation did not settle enough facts to draft from.",
    "demands nothing": "The draft came back without a demand in it.",
    "not retrieved": (
        "The draft cited law this conversation never established, so it was refused."
    ),
}


def in_plain_words(failures: str) -> str:
    """A failure a reader can act on, or the original if none matches."""
    for marker, plain in _IN_PLAIN_WORDS.items():
        if marker in failures:
            return plain
    return failures


def fail(conn: psycopg.Connection, draft_id: str, error: str) -> None:
    """Record why a draft could not be produced, in the reader's terms.

    A failed draft keeps its row. A document that silently never appears is
    indistinguishable from one still being written.
    """
    error = in_plain_words(error)
    conn.execute(
        "UPDATE drafts SET status = 'failed', error = %s, finished_at = now() "
        "WHERE draft_id = %s",
        (error[:2000], draft_id),
    )
    conn.commit()


def get(conn: psycopg.Connection, draft_id: str, user_id: str) -> dict | None:
    """One draft, without its bytes, or None if it is not this user's.

    The join on the thread is what enforces ownership: drafts carry no
    user_id of their own, so a draft is this user's exactly when its thread
    is.
    """
    row = conn.execute(
        """
        SELECT d.draft_id, d.thread_id, d.document_type, d.status, d.filename,
               d.structure, d.error, d.created_at, d.finished_at,
               (d.docx IS NOT NULL) AS has_file
        FROM drafts d JOIN threads t USING (thread_id)
        WHERE d.draft_id = %s AND t.user_id = %s
        """,
        (draft_id, user_id),
    ).fetchone()
    return _as_dict(row) if row else None


def content(conn: psycopg.Connection, draft_id: str, user_id: str) -> tuple[str, bytes] | None:
    """`(filename, bytes)` for download, or None if it is not this user's."""
    row = conn.execute(
        """
        SELECT d.filename, d.docx FROM drafts d JOIN threads t USING (thread_id)
        WHERE d.draft_id = %s AND t.user_id = %s AND d.docx IS NOT NULL
        """,
        (draft_id, user_id),
    ).fetchone()
    return (row[0], bytes(row[1])) if row else None


def for_thread(conn: psycopg.Connection, thread_id: str, user_id: str) -> Page[dict]:
    """Every draft on this thread, oldest first.

    Oldest first because these render in a conversation, under the messages
    and above the composer. Newest-first put the document someone had just
    asked for at the top of the thread, furthest from the button they
    pressed.
    """
    rows = conn.execute(
        """
        SELECT d.draft_id, d.thread_id, d.document_type, d.status, d.filename,
               d.structure, d.error, d.created_at, d.finished_at,
               (d.docx IS NOT NULL) AS has_file
        FROM drafts d JOIN threads t USING (thread_id)
        WHERE d.thread_id = %s AND t.user_id = %s
        ORDER BY d.created_at ASC
        """,
        (thread_id, user_id),
    ).fetchall()
    items = [_as_dict(row) for row in rows]
    return Page(items=items, total=len(items), limit=len(items), offset=0)


def running_on(conn: psycopg.Connection, thread_id: str) -> bool:
    """Whether a draft is already being prepared for this thread.

    One at a time: two drafts of one thread racing would leave the reader
    two cards and no way to tell which is the document they asked for.
    """
    return (
        conn.execute(
            "SELECT 1 FROM drafts WHERE thread_id = %s AND status = 'running'",
            (thread_id,),
        ).fetchone()
        is not None
    )


def _as_dict(row) -> dict:
    return {
        "draft_id": row[0],
        "thread_id": row[1],
        "document_type": row[2],
        "status": row[3],
        "filename": row[4],
        "structure": row[5],
        "error": row[6],
        "created_at": row[7],
        "finished_at": row[8],
        "has_file": row[9],
    }
