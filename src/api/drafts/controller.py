"""Draft a document from a thread.

The run is detached from the request for the same reason a researched turn
is: it takes a model call and a render, and a reader who closes the tab
must not lose a document they already paid for. The request returns a
draft_id at once; the reader watches `status` and the file appears.

One draft at a time per thread. Two racing would leave the reader two cards
and no way to tell which is the document they asked for -- the same
guarantee the runs table will one day enforce with a unique index, done
here with a check because the table does not exist yet.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import asdict
from datetime import date

from api.databases.postgres import connection
from api.drafts import repository
from api.threads.repository import get_thread, list_messages
from api.utils.errors import Ok, Result, conflict, invalid_request, not_found

log = logging.getLogger(__name__)

# What a downloaded file is called. The thread's title is the reader's own
# words, so it is what they will look for in a downloads folder.
FILENAME_CHARS = 60

# In-flight drafts. Held so the loop cannot collect one mid-run; asyncio
# keeps only a weak reference to a task nobody awaits.
_RUNS: set[asyncio.Task] = set()


async def start_draft(conn, user_id: str, thread_id: str, document_type: str) -> Result:
    """Begin a draft and return its id, without waiting for it."""
    from legal_ai.drafting import DOCUMENT_TYPES, available_types
    from legal_ai.drafting.source import thread_authorities

    thread = get_thread(conn, thread_id, user_id)
    if thread is None:
        return not_found("thread")

    known = next((t for t in DOCUMENT_TYPES if t.value == document_type), None)
    if known is None:
        return invalid_request(f"No template for document type {document_type!r}.")

    # Refused here rather than after a model call. A document type the
    # conversation holds no law for can only come back empty, and the reader
    # should be told why in their own terms rather than shown a validator's.
    authorities = thread_authorities(list_messages(conn, thread_id, user_id))
    if known not in available_types(authorities):
        return invalid_request(
            f"This conversation has not established the law a "
            f"{known.label.lower()} rests on. Ask about that first, then draft."
        )

    if repository.running_on(conn, thread_id):
        return conflict(
            "draft_in_progress",
            "A document is already being prepared for this thread.",
        )

    draft_id = repository.start(conn, thread_id, document_type)
    conn.commit()

    run = asyncio.create_task(
        _draft_and_store(
            draft_id=draft_id,
            thread_id=thread_id,
            user_id=user_id,
            case_id=thread.case_id,
            document_type=document_type,
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
    document_type: str,
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
            if not authorities:
                repository.fail(
                    conn,
                    draft_id,
                    "This conversation has not established any law yet. Ask a "
                    "question first, then draft from the answer.",
                )
                return

            matter = thread_matter(conn, case_id, date.today())
            conversation = thread_conversation(messages)
            law = render_law(conn, authorities)
        # The model call runs with no connection held. CLAUDE.md section 8.

        result = await asyncio.to_thread(
            run_draft, document_type, matter, conversation, law, authorities
        )

        with connection() as conn:
            if result.structure is None or result.failures:
                repository.fail(conn, draft_id, "; ".join(result.failures))
                return
            docx = render_with_citations(conn, result.structure)
            repository.finish(
                conn, draft_id, _filename(document_type, title),
                asdict(result.structure), docx,
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


def draftable(conn, user_id: str, thread_id: str) -> Result:
    """The document types this thread has established the law for.

    Offering one it has not is how a reader on a conspiracy thread was
    shown a cheque-bounce notice, waited for it, and got a failure.
    """
    from legal_ai.drafting import available_types
    from legal_ai.drafting.source import thread_authorities

    if get_thread(conn, thread_id, user_id) is None:
        return not_found("thread")

    authorities = thread_authorities(list_messages(conn, thread_id, user_id))
    return Ok([
        {"value": t.value, "label": t.label} for t in available_types(authorities)
    ])


def download(conn, user_id: str, draft_id: str) -> Result:
    found = repository.content(conn, draft_id, user_id)
    if found is None:
        return not_found("draft")
    filename, data = found
    return Ok({"filename": filename, "content": data})


def _filename(document_type: str, title: str) -> str:
    """A name the reader will recognise in a downloads folder."""
    words = "".join(
        character if character.isalnum() or character in " -_" else " "
        for character in (title or document_type)
    ).split()
    stem = "_".join(words)[:FILENAME_CHARS].strip("_").lower()
    return f"{stem or document_type}.docx"
