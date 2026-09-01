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

import logging

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
log = logging.getLogger(__name__)

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

    clarification = None
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

        # The graph can halt to ask for a missing fact. That is a real
        # outcome, not an empty answer: dropping it leaves the user with a
        # blank reply and no idea what to do next.
        clarification = state.get("clarification_needed")
        if clarification and not answer:
            text = clarification

    add_message(conn, thread_id, "user", message)
    add_message(conn, thread_id, "assistant", text or "", answer=answer)

    # A thread in a case leaves its conclusions behind. Without this the
    # case carries documents forward but not findings, and the fourth
    # question re-derives what the first three settled -- which is the whole
    # reason the container exists.
    if thread.case_id and route is Route.RESEARCH and answer is not None:
        _remember(conn, thread.case_id, message, answer)

    if thread.title == "New thread":
        set_title(conn, thread_id, user_id, message[:TITLE_CHARS])

    return Ok({
        "text": text,
        "answer": answer,
        "clarification_needed": clarification,
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


def _remember(conn, case_id: str, question: str, answer: dict) -> None:
    """Record what this turn established against the case.

    Only claims that survived verification. A claim the checker rejected, or
    never looked at, must not become a fact the next question is seeded
    with -- that would launder an unverified statement into the case file.

    Failures are swallowed: losing a finding costs the next question some
    context, while failing the request costs the user the answer they
    already paid for.
    """
    from legal_ai.case.models import EstablishedFinding
    from legal_ai.case.session import save_to_case

    findings = tuple(
        EstablishedFinding(
            claim=claim["text"],
            evidence_ids=tuple(claim.get("evidence_ids") or ()),
            source_case_id=case_id,
        )
        for claim in answer.get("key_elements") or []
        if claim.get("text") and claim.get("evidence_ids")
    )
    try:
        save_to_case(conn, case_id, question, findings=findings)
    except Exception:
        log.warning("could not record findings for case %s", case_id, exc_info=True)


async def stream_message(
    conn,
    user_id: str,
    thread_id: str,
    message: str,
    document_ids: list[str] | None = None,
    verification_level: str | None = None,
):
    """`send_message`, yielding progress as it goes.

    Deliberately a separate function rather than a flag on `send_message`.
    The two differ only in how they report, and a boolean that changes a
    return type from a value to a generator is the kind of signature nobody
    reads correctly.
    """
    from api.threads.graph import STEP_LABELS, research_with_progress

    thread = get_thread(conn, thread_id, user_id)
    if thread is None:
        yield "error", {"code": "not_found", "message": "No such thread."}
        return

    if verification_level is None:
        verification_level = Configuration.from_env().verification_level

    history = _history(conn, thread_id, user_id)
    route = route_message(message, history)

    if route is Route.ANSWER:
        # Nothing to report on: it never touched the corpus.
        text = answer_from_history(message, history)
        add_message(conn, thread_id, "user", message)
        add_message(conn, thread_id, "assistant", text or "")
        yield "done", {
            "text": text, "answer": None, "clarification_needed": None,
            "route": route.value, "verification_level": verification_level,
        }
        return

    state = None
    async for kind, payload in research_with_progress({
        "question": rewrite_question(message, history),
        "case_id": thread.case_id,
        "document_ids": list(document_ids or []),
        "verification_level": verification_level,
    }):
        if kind == "step":
            yield "step", {"node": payload, "label": STEP_LABELS.get(payload, payload)}
        elif kind == "error":
            # Nothing is stored: a half-turn would be resolved against by the
            # next rewrite as though it were an answer.
            yield "error", {"code": "internal_error", "message": "Research failed."}
            return
        else:
            state = payload

    text = (state or {}).get("answer")
    answer = _as_dict((state or {}).get("draft_answer"))
    clarification = (state or {}).get("clarification_needed")
    if clarification and not answer:
        text = clarification

    add_message(conn, thread_id, "user", message)
    add_message(conn, thread_id, "assistant", text or "", answer=answer)
    if thread.title == "New conversation":
        set_title(conn, thread_id, user_id, message[:TITLE_CHARS])
    if thread.case_id and answer is not None:
        _remember(conn, thread.case_id, message, answer)

    yield "done", {
        "text": text, "answer": answer, "clarification_needed": clarification,
        "route": route.value, "verification_level": verification_level,
    }
