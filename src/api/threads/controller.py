"""One turn of a thread.

Where the phase's two findings meet. A follow-up is rewritten before it
reaches retrieval, because "what about Bombay" retrieves nothing on its own.
A message about the answer already given is answered from it, rather than
re-running a thirty-second fan-out to re-find what is on screen.

Both fallbacks point the same way -- towards doing more work, never less. A
broken rewriter sends the user's own words; an uncertain route researches.

The rewrite is a retrieval device and is never stored. Showing it back would
rewrite the user's own history at them.
"""

from __future__ import annotations

from api.threads.repository import (
    add_message,
    get_thread,
    list_messages,
    set_title,
)
from api.utils.errors import Failure, Ok, Result, not_found
from legal_ai.config import Configuration
from api.threads.graph import research as run_research
from legal_ai.conversation.rewriter import Turn, rewrite_question
from legal_ai.conversation.router import Route, route_message

# Turns of history handed to the rewriter and the router. Bounded because
# accuracy falls when the current question sits mid-context, not to save
# tokens.
HISTORY_TURNS = 8

# Characters of the first message used as a thread title. A sidebar of
# "New thread" is unusable.
TITLE_CHARS = 60


def _history(conn, thread_id: str, user_id: str) -> list[Turn]:
    return [
        Turn(role=message.role, content=message.content)
        for message in list_messages(conn, thread_id, user_id)[-HISTORY_TURNS:]
    ]


def answer_from_history(question: str, history: list[Turn]) -> str:
    """Answer a question about the reply already given.

    Deliberately not implemented as a model call yet. Until there is one,
    routing here returns the last answer verbatim, which is honest -- it is
    what the user is asking about -- and it never invents law. Milestone 18
    replaces this with a bounded call over the stored claims.
    """
    for turn in reversed(history):
        if turn.role == "assistant":
            return turn.content
    return ""


async def send_message(
    conn,
    user_id: str,
    thread_id: str,
    message: str,
    document_ids: list[str] | None = None,
    verification_level: str | None = None,
) -> Result:
    """Add `message` to the thread and answer it.

    A missing thread and someone else's thread are the same
    404: telling a caller a thread exists but is not theirs confirms the id.
    """
    thread = get_thread(conn, thread_id, user_id)
    if thread is None:
        return not_found("thread")

    if verification_level is None:
        verification_level = Configuration.from_env().verification_level

    history = _history(conn, thread_id, user_id)
    route = route_message(message, history)

    if route is Route.ANSWER:
        text, answer = answer_from_history(message, history), None
    else:
        # Only the rewritten question reaches retrieval.
        # The thread's own case and documents, not the request's: a caller
        # must not be able to read another matter by naming its id.
        result = await run_research(
            {
                "question": rewrite_question(message, history),
                "case_id": thread.case_id,
                "document_ids": list(document_ids or []),
                "verification_level": verification_level,
            }
        )
        if isinstance(result, Failure):
            # Nothing is stored. A half-turn in the thread would be resolved
            # against by the next rewrite as though it were an answer.
            return result
        state = result.value
        text = state.get("answer")
        draft = state.get("draft_answer")
        answer = _as_dict(draft)

    add_message(conn, thread_id, "user", message)
    add_message(conn, thread_id, "assistant", text or "", answer=answer)

    if thread.title == "New thread":
        set_title(conn, thread_id, user_id, message[:TITLE_CHARS])

    return Ok({
        "text": text,
        "answer": answer,
        "route": route.value,
        "verification_level": verification_level,
    })


def _as_dict(draft) -> dict | None:
    """The structured answer, as JSON, so a later turn can cite what was
    established rather than re-deriving it."""
    if draft is None:
        return None
    from api.schemas import AnswerModel

    return AnswerModel.of(draft).model_dump()
