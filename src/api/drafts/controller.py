"""Draft a document from a thread.

The run is detached from the request for the same reason a researched turn
is: it takes a model call and a render, and a reader who closes the tab
must not lose a document they already paid for. The request returns a
draft_id at once; the reader watches `status` and the file appears.

Nothing is chosen. The model reads what was asked and what the conversation
settled, and produces the document that follows from it -- there was a
document type to pick, and it could only offer the one instrument a
template existed for.

One draft at a time per thread. Two racing would leave the reader two cards
and no way to tell which is the document they asked for.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import asdict
from datetime import date

from api.databases.postgres import connection
from api.drafts import repository
from api.threads.repository import get_thread, list_messages
from api.utils.errors import Ok, Result, conflict, not_found

log = logging.getLogger(__name__)

# What a downloaded file is called. The document's own title is what the
# reader will look for in a downloads folder.
FILENAME_CHARS = 60

# In-flight drafts. Held so the loop cannot collect one mid-run; asyncio
# keeps only a weak reference to a task nobody awaits.
_RUNS: set[asyncio.Task] = set()


async def start_draft(conn, user_id: str, thread_id: str) -> Result:
    """Begin a draft and return its id, without waiting for it."""
    thread = get_thread(conn, thread_id, user_id)
    if thread is None:
        return not_found("thread")

    if repository.running_on(conn, thread_id):
        return conflict(
            "draft_in_progress",
            "A document is already being prepared for this thread.",
        )

    draft_id = repository.start(conn, thread_id)
    conn.commit()

    run = asyncio.create_task(
        _draft_and_store(
            draft_id=draft_id,
            thread_id=thread_id,
            user_id=user_id,
            case_id=thread.case_id,
            title=thread.title,
        )
    )
    _RUNS.add(run)
    run.add_done_callback(_RUNS.discard)

    return Ok({"draft_id": draft_id, "status": "running"})


async def _draft_and_store(
    draft_id: str,
    thread_id: str,
    user_id: str,
    case_id: str | None,
    title: str,
) -> None:
    """Draft the document and store it, read or not.

    Its own connection: the request's went back to the pool when the reply
    was sent, and this outlives that.
    """
    from legal_ai.drafting import draft as run_draft
    from legal_ai.drafting.render import render_with_citations
    from legal_ai.drafting.source import (
        render_law,
        thread_authorities,
        thread_conversation,
        thread_matter,
    )

    try:
        with connection() as conn:
            messages = list_messages(conn, thread_id, user_id)
            authorities = thread_authorities(messages)
            matter = thread_matter(conn, case_id, date.today())
            conversation = thread_conversation(messages)
            law = render_law(conn, authorities)
        # The model call runs with no connection held. CLAUDE.md section 8.

        result = await asyncio.to_thread(
            run_draft, matter, conversation, law, authorities
        )

        with connection() as conn:
            if result.structure is None or result.failures:
                repository.fail(conn, draft_id, "; ".join(result.failures))
                return
            docx = render_with_citations(conn, result.structure)
            repository.finish(
                conn,
                draft_id,
                _filename(result.structure.title, title),
                asdict(result.structure),
                docx,
            )
    except Exception:
        # Nobody is left to raise to: this runs outside the request.
        log.exception("draft %s failed for thread %s", draft_id, thread_id)
        try:
            with connection() as conn:
                repository.fail(conn, draft_id, "The document could not be prepared.")
        except Exception:
            log.exception("could not record the failure of draft %s", draft_id)


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


def _filename(document_title: str, thread_title: str) -> str:
    """A name the reader will recognise in a downloads folder.

    The document's own title first -- "legal opinion", "notice under section
    138" -- since that is what they asked for; the thread's title only where
    the draft came back without one.
    """
    words = "".join(
        character if character.isalnum() or character in " -_" else " "
        for character in (document_title or thread_title)
    ).split()
    stem = "_".join(words)[:FILENAME_CHARS].strip("_").lower()
    return f"{stem or 'draft'}.docx"
