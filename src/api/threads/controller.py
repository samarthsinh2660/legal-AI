"""Accepting a message.

The whole of what the API does for a turn: check the thread is this user's,
store the question, and put a job on the queue. The answering happens in
`src/worker/`, on possibly another machine, and reaches the reader over
`GET /runs/{run_id}/stream`.

The question is stored here rather than by the worker so that it is on
screen the instant the request returns, and survives a refresh taken a
second later. A researched turn takes 30-130 seconds, and a tab closed
anywhere in that window used to lose the question outright -- nothing was
written until the very end, so a disconnect left the thread looking exactly
like nobody had asked anything. Reproduced live 2026-09-03 on thread
714851b0, which landed back on "Ask your first question below."
"""

from __future__ import annotations

from api.runs import repository as runs
from api.threads.repository import DEFAULT_TITLE, add_message, get_thread, set_title
from api.utils.errors import Ok, Result, conflict, not_found

# Characters of the first message used as a thread title. A sidebar of
# "New thread" is unusable.
TITLE_CHARS = 60


def send_message(
    conn,
    user_id: str,
    thread_id: str,
    message: str,
    document_ids: list[str] | None = None,
    verification_level: str | None = None,
) -> Result:
    """Queue `message` for answering and return the run that will answer it.

    A missing thread and someone else's thread are the same 404: telling a
    caller a thread exists but is not theirs confirms the id.

    One research run per thread. Two turns answering the same thread at
    once would interleave their messages and each rewrite the other's
    follow-up against a history that was still moving. A draft alongside
    one is fine: it reads the thread and writes nothing to it.
    """
    from legal_ai.config import Configuration

    thread = get_thread(conn, thread_id, user_id)
    if thread is None:
        return not_found("thread")

    if runs.live_for_thread(conn, thread_id, user_id, kind="research") is not None:
        return conflict(
            "run_in_progress", "This thread is still working on the last message."
        )

    if verification_level is None:
        verification_level = Configuration.from_env().verification_level

    stored = add_message(conn, thread_id, "user", message)
    if thread.title == DEFAULT_TITLE:
        set_title(conn, thread_id, user_id, message[:TITLE_CHARS])

    run_id = runs.enqueue(conn, thread_id, user_id, "research", {
        "message": message,
        # Which message this is, so the worker can read the history as it
        # stood before it -- otherwise the rewriter is handed the very
        # question it is rewriting.
        "message_id": stored.message_id,
        "document_ids": _permitted_documents(conn, thread.case_id, document_ids),
        "verification_level": verification_level,
    })
    return Ok({"run_id": run_id, "thread_id": thread_id, "status": "queued"})


def _permitted_documents(conn, case_id: str | None, requested) -> list[str]:
    """The requested ids, kept only if they belong to this thread's case.

    `get_case_file_text` looks a document up by id alone, with no owner and
    no case filter, so anything not checked here is readable by anyone who
    has ever seen the id. Checked at the door rather than in the worker: the
    job row is trusted input by the time a worker reads it.

    An empty `requested` defaults to every file the case holds, rather than
    to none: the chat composer sends no per-message document_ids on a case
    thread, so a case's own uploaded file must otherwise be reached some
    other way.
    """
    if case_id is None:
        # A thread outside a case has no files it may read.
        return []
    from legal_ai.case.files import list_case_files

    allowed = {document_id for document_id, _filename in list_case_files(conn, case_id)}
    if not requested:
        return list(allowed)
    return [document_id for document_id in requested if document_id in allowed]
