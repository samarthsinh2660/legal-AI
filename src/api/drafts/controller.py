"""Asking for a document to be drafted.

The API's whole part in it: check the thread, create the draft row and
queue the job. The drafting itself is `worker/drafting.py` -- it takes a
model call and a render, and a reader who closes the tab must not lose a
document they already paid for.

Nothing is chosen. The model reads what was asked and what the conversation
settled, and produces the document that follows from it -- there was a
document type to pick, and it could only offer the one instrument a
template existed for.

One draft at a time per thread. Two racing would leave the reader two cards
and no way to tell which is the document they asked for.
"""

from __future__ import annotations

from api.drafts import repository
from api.runs import repository as runs
from api.threads.repository import get_thread
from api.utils.errors import Ok, Result, conflict, not_found


def start_draft(conn, user_id: str, thread_id: str) -> Result:
    """Queue a draft and return its id, without waiting for it."""
    thread = get_thread(conn, thread_id, user_id)
    if thread is None:
        return not_found("thread")

    if repository.running_on(conn, thread_id):
        return conflict(
            "draft_in_progress",
            "A document is already being prepared for this thread.",
        )

    draft_id = repository.start(conn, thread_id)
    runs.enqueue(conn, thread_id, user_id, "draft", {"draft_id": draft_id})
    conn.commit()

    return Ok({"draft_id": draft_id, "status": "running"})


def get_draft(conn, user_id: str, draft_id: str) -> Result:
    draft = repository.get(conn, draft_id, user_id)
    if draft is None:
        return not_found("draft")
    return Ok(draft)


def list_drafts(conn, user_id: str, thread_id: str) -> Result:
    if get_thread(conn, thread_id, user_id) is None:
        return not_found("thread")
    return Ok(repository.for_thread(conn, thread_id, user_id))


def download(conn, user_id: str, draft_id: str) -> Result:
    found = repository.content(conn, draft_id, user_id)
    if found is None:
        return not_found("draft")
    filename, data = found
    return Ok({"filename": filename, "content": data})
