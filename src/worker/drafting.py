"""Draft a document from a thread, run by the worker.

A job for the same reason a researched turn is one: it takes a model call
and a render, and a reader who closes the tab must not lose a document they
already paid for.

Nothing is chosen. The model reads what was asked and what the conversation
settled, and produces the document that follows from it -- there was a
document type to pick, and it could only ever offer the one instrument a
template existed for.

The result lives in `drafts`, not in the run: the run is the queue entry and
the progress, the draft row is the file. Finishing both in one place is what
keeps a reader from seeing a completed run with no document under it.
"""

from __future__ import annotations

import logging
from dataclasses import asdict
from datetime import date

from api.databases.postgres import connection
from api.drafts import repository
from api.runs import repository as runs
from api.threads.repository import get_thread, list_messages

log = logging.getLogger(__name__)

# What a downloaded file is called. The document's own title is what the
# reader will look for in a downloads folder.
FILENAME_CHARS = 60


def run(job: dict) -> None:
    """Draft one document and store it. Nothing raises out of here."""
    from api.drafts.source import (
        render_law,
        thread_authorities,
        thread_conversation,
        thread_matter,
    )
    from legal_ai.agents.drafter import draft as run_draft
    from legal_ai.agents.drafter import render_with_citations

    run_id = job["run_id"]
    thread_id = job["thread_id"]
    user_id = job["user_id"]
    draft_id = job["payload"]["draft_id"]

    try:
        with connection() as conn:
            # The one place a draft can be interrupted, and the only place
            # it can say it is alive. Everything after this is a single
            # model call with no seam inside it -- so without a beat here
            # the heartbeat stays as `claim` left it, and a draft slower
            # than STALE_AFTER_SECONDS is requeued while it is still being
            # written. Two workers then finish the same draft row.
            if runs.beat(conn, run_id) != "running":
                log.info("run %s is no longer wanted; not drafting", run_id)
                return
            thread = get_thread(conn, thread_id, user_id)
            messages = list_messages(conn, thread_id, user_id)
            authorities = thread_authorities(messages)
            matter = thread_matter(conn, thread.case_id if thread else None, date.today())
            conversation = thread_conversation(messages)
            law = render_law(conn, authorities)
        # The model call runs with no connection held: a transaction left
        # open across it queues every other writer behind a model round-trip.

        result = run_draft(matter, conversation, law, authorities)

        with connection() as conn:
            if result.structure is None or result.failures:
                reason = "; ".join(result.failures) or "The document could not be prepared."
                repository.fail(conn, draft_id, reason)
                runs.fail(conn, run_id, "draft_failed", reason)
                return
            docx = render_with_citations(conn, result.structure)
            repository.finish(
                conn,
                draft_id,
                _filename(result.structure.title, thread.title if thread else ""),
                asdict(result.structure),
                docx,
            )
            runs.finish(conn, run_id, {"draft_id": draft_id})
    except Exception:
        log.exception("draft %s failed for thread %s", draft_id, thread_id)
        try:
            with connection() as conn:
                repository.fail(conn, draft_id, "The document could not be prepared.")
                runs.fail(conn, run_id, "internal_error",
                          "The document could not be prepared.")
        except Exception:
            log.exception("could not record the failure of draft %s", draft_id)


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
