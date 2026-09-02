"""One turn of a thread.

Where the phase's two findings meet. A follow-up is rewritten before it
reaches retrieval, because "what about Bombay" retrieves nothing on its own.
A message the router judges answerable from the thread is composed out of the
claims the thread already established, rather than re-running a
thirty-second fan-out to re-find what is on screen.

Both fallbacks point the same way -- towards doing more work, never less. A
broken rewriter sends the user's own words; an uncertain route researches.

The rewrite is a retrieval device and is never stored. Showing it back would
rewrite the user's own history at them.
"""

from __future__ import annotations

import logging

from api.threads.repository import (
    DEFAULT_TITLE,
    recent_answers,
    recent_turns,
    add_message,
    get_thread,
    list_messages,
    set_title,
)
from api.utils.errors import Failure, Ok, Result, not_found
from legal_ai.agents.draft import render
from legal_ai.config import Configuration
from api.threads.graph import research as run_research
from legal_ai.conversation.recall import answer_from_thread
from legal_ai.conversation.rewriter import Turn, rewrite_question
from legal_ai.conversation.intent import Intent, classify, reply_for
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
        for message in recent_turns(conn, thread_id, user_id, HISTORY_TURNS)
    ]


# What an ANSWER turn says when the thread cannot answer the question.
# Until 2026-09 this path returned the previous assistant turn verbatim, so a
# new question got the old answer with nothing on screen saying so. Composing
# over the stored claims replaces that; where composition finds nothing, the
# reply says nothing was found. It does not fall back to the replay, and it
# does not silently research -- a turn that never touched the corpus must not
# read like one that did.
COULD_NOT_ANSWER = (
    "I could not answer that from this conversation. Nothing established in "
    "the thread so far addresses it, and this turn did not search the corpus. "
    "Ask it as a fresh question to have it researched."
)


def answer_from_thread_turn(conn, user_id: str, thread_id: str, message: str):
    """The ANSWER route's reply: `(text, answer)`.

    `answer` is None when the thread held nothing that answers the question,
    which the caller renders as `COULD_NOT_ANSWER` rather than as an answer.

    The read is committed before the composition call. Holding the
    transaction across it queues every writer behind a model round-trip --
    CLAUDE.md section 8.
    """
    stored = recent_answers(conn, thread_id, user_id, HISTORY_TURNS)
    conn.commit()

    composed = answer_from_thread(message, stored)
    if composed is None:
        return COULD_NOT_ANSWER, None
    return render(composed), _as_dict(composed)


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
    # Everything the graph needs is read now, and the connection is released
    # before the run. Holding it for the 100+ seconds of a research call
    # exhausts a pool of ten after ten concurrent messages, and every other
    # request -- including the auth check and /health -- then waits out the
    # borrow timeout and fails. CLAUDE.md section 8.
    conn.commit()

    if verification_level is None:
        verification_level = Configuration.from_env().verification_level

    # A greeting is settled by a pattern, not a model. Before this gate the
    # planner was asked to plan a corpus search for it and had no way to
    # decline, so "thanks!" cost 80s and came back with the law on gratuity.
    small_talk = reply_for(classify(message))
    if small_talk is not None:
        add_message(conn, thread_id, "user", message)
        add_message(conn, thread_id, "assistant", small_talk)
        return Ok({
            "text": small_talk, "answer": None, "clarification_needed": None,
            "route": Route.ANSWER.value, "verification_level": verification_level,
        })

    history = _history(conn, thread_id, user_id)
    route = route_message(message, history)

    clarification = None
    if route is Route.ANSWER:
        text, answer = answer_from_thread_turn(conn, user_id, thread_id, message)
    else:
        # Only the rewritten question reaches retrieval.
        # Both the case and the documents are the thread's own. The ids in
        # the request are filtered against the case's files first: a
        # document_id seen once -- from a detached case, a shared link --
        # would otherwise read that file's full text into any answer,
        # forever.
        result = await run_research(
            {
                "question": rewrite_question(message, history),
                "case_id": thread.case_id,
                "document_ids": _permitted_documents(conn, thread.case_id, document_ids),
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

    if thread.title == DEFAULT_TITLE:
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

    small_talk = reply_for(classify(message))
    if small_talk is not None:
        add_message(conn, thread_id, "user", message)
        add_message(conn, thread_id, "assistant", small_talk)
        yield "done", {
            "text": small_talk, "answer": None, "clarification_needed": None,
            "route": Route.ANSWER.value, "verification_level": verification_level,
        }
        return

    history = _history(conn, thread_id, user_id)
    route = route_message(message, history)

    if route is Route.ANSWER:
        # No steps to report on: it never touched the corpus.
        text, answer = answer_from_thread_turn(conn, user_id, thread_id, message)
        add_message(conn, thread_id, "user", message)
        add_message(conn, thread_id, "assistant", text or "", answer=answer)
        yield "done", {
            "text": text, "answer": answer, "clarification_needed": None,
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
        elif kind == "timeout":
            # Nothing is stored: a half-turn would be resolved against by the
            # next rewrite as though it were an answer.
            yield "error", {
                "code": "timeout",
                "message": "Research did not finish within the time limit.",
            }
            return
        elif kind == "error":
            log.warning("research failed mid-stream", exc_info=payload)
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
    if thread.title == DEFAULT_TITLE:
        set_title(conn, thread_id, user_id, message[:TITLE_CHARS])
    if thread.case_id and answer is not None:
        _remember(conn, thread.case_id, message, answer)

    yield "done", {
        "text": text, "answer": answer, "clarification_needed": clarification,
        "route": route.value, "verification_level": verification_level,
    }


def _permitted_documents(conn, case_id: str | None, requested) -> list[str]:
    """The requested ids, kept only if they belong to this thread's case.

    `get_case_file_text` looks a document up by id alone, with no owner and
    no case filter, so anything not checked here is readable by anyone who
    has ever seen the id.
    """
    if not requested:
        return []
    if case_id is None:
        # A thread outside a case has no files it may read.
        return []
    from legal_ai.case.files import list_case_files

    allowed = {document_id for document_id, _filename in list_case_files(conn, case_id)}
    return [document_id for document_id in requested if document_id in allowed]
