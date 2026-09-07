"""One turn of a thread, run by the worker.

Two things decide what a turn costs. A follow-up is rewritten into a
standalone question before it reaches retrieval, because "what about
Bombay" retrieves nothing on its own. And a message the router judges
answerable from the thread is composed out of the claims already
established, rather than re-running a thirty-second fan-out to re-find what
is already on screen.

Both fallbacks point the same way -- towards doing more work, never less. A
broken rewriter sends the user's own words; an uncertain route researches.

The rewrite is a retrieval device and is never stored. Showing it back would
rewrite the user's own history at them.

Everything this needs is in the job row. The API stored the question and
enqueued; nothing here reads a request, which is what lets the worker run
somewhere else entirely.
"""

from __future__ import annotations

import logging

from api.databases.postgres import connection
from api.runs import repository as runs
from api.threads.repository import (
    add_message,
    get_thread,
    recent_answers,
    recent_turns,
)
from legal_ai.agents.draft import render
from legal_ai.conversation.intent import classify, reply_for
from legal_ai.conversation.recall import answer_from_thread
from legal_ai.conversation.rewriter import Turn, rewrite_question
from legal_ai.conversation.router import Route, route_message
from worker.graph import STEP_LABELS, stream_graph

log = logging.getLogger(__name__)

# Turns of history handed to the rewriter and the router. Bounded because
# accuracy falls when the current question sits mid-context, not to save
# tokens.
HISTORY_TURNS = 8

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


def run(job: dict) -> None:
    """Answer one enqueued question and record the result.

    Nothing raises out of here. The caller is a loop with no reader to
    report to, and a job that fails without closing its row leaves a thread
    saying "still researching" for good.
    """
    run_id = job["run_id"]
    thread_id = job["thread_id"]
    user_id = job["user_id"]
    payload = job["payload"]
    message = payload["message"]
    verification_level = payload["verification_level"]

    try:
        with connection() as conn:
            thread = get_thread(conn, thread_id, user_id)
            history = _history(conn, thread_id, user_id, payload["message_id"])
        if thread is None:
            _fail(run_id, "not_found", "No such thread.")
            return

        # A greeting is settled by a pattern, not a model. Before this gate
        # the planner was asked to plan a corpus search for it and had no way
        # to decline, so "thanks!" cost 80s and came back with the law on
        # gratuity.
        small_talk = reply_for(classify(message))
        if small_talk is not None:
            _reply(run_id, thread_id, small_talk, None, None,
                   Route.ANSWER, verification_level)
            return

        route = route_message(message, history)

        if route is Route.ANSWER:
            # No steps to report on: it never touched the corpus.
            text, answer = _answer_from_thread(thread_id, user_id, message)
            _reply(run_id, thread_id, text, answer, None,
                   Route.ANSWER, verification_level)
            return

        _research(
            run_id=run_id,
            thread_id=thread_id,
            case_id=thread.case_id,
            message=message,
            history=history,
            document_ids=payload.get("document_ids") or [],
            verification_level=verification_level,
        )
    except Exception:
        log.exception("run %s failed for thread %s", run_id, thread_id)
        _fail(run_id, "internal_error", "Research failed.")


def _research(
    run_id: str,
    thread_id: str,
    case_id: str | None,
    message: str,
    history: list[Turn],
    document_ids: list[str],
    verification_level: str,
) -> None:
    """The RESEARCH route: the graph, its progress, and the stored answer."""
    from legal_ai.context.clarification import DATE_QUESTION, STATE_QUESTION

    question = rewrite_question(message, history)
    state: dict = {}

    # What a previous attempt found, if the reaper handed this run on. The
    # graph skips searching when it is given evidence on its first round,
    # so a retry costs the analysis again but not the search.
    with connection() as conn:
        carried = runs.restore_findings(conn, run_id)
    if carried:
        log.info("run %s: resuming with %d findings", run_id, len(carried))

    for kind, produced in stream_graph({
        "question": question,
        "case_id": case_id,
        "document_ids": document_ids,
        "verification_level": verification_level,
        "findings": carried,
        "clarification_asked": _already_clarified(history, {STATE_QUESTION, DATE_QUESTION}),
    }):
        # The one seam a synchronous graph offers. Everything that needs to
        # interrupt a run happens here: a thread deleted out from under it,
        # a reader who cancelled, and the beat that tells the reaper this
        # worker is alive rather than dead holding a row.
        stop = _stop_reason(run_id)
        if stop:
            log.info("run %s: %s", run_id, stop)
            return
        if kind == "step":
            with connection() as conn:
                runs.step(conn, run_id, produced, STEP_LABELS.get(produced, produced))
        elif kind == "findings":
            # Stored the moment retrieval is done, not at the end: the
            # point is to survive a worker that dies after this.
            with connection() as conn:
                runs.save_findings(conn, run_id, produced)
        elif kind == "timeout":
            # The question survives; no assistant reply is written, so there
            # is nothing here for a later rewrite to mistake for an answer.
            _fail(run_id, "timeout",
                  "Research did not finish within the time limit.")
            return
        elif kind == "error":
            log.warning("research failed mid-run", exc_info=produced)
            _fail(run_id, "internal_error", "Research failed.")
            return
        else:
            state = produced or {}

    text = state.get("answer")
    answer = _as_dict(state.get("draft_answer"))
    clarification = state.get("clarification_needed")
    if clarification and not answer:
        text = clarification

    # The lede in pieces, ahead of "done" -- and only the lede, only once it
    # is final. Streaming the analyst's own generation would show a reader
    # prose that verification could still move into a weaker bucket, which is
    # the false reassurance every three-state check here exists to prevent.
    # Chunking a finished answer is the safe version of the same win: the
    # reader starts reading before claims and sources have rendered.
    stop = _stop_reason(run_id)
    if stop:
        log.info("run %s: %s", run_id, stop)
        return

    lede = (answer or {}).get("lede") if answer else None
    if lede:
        with connection() as conn:
            for chunk in _chunk_words(lede):
                runs.append(conn, run_id, "answer_chunk", {"text": chunk})

    _reply(run_id, thread_id, text, answer, clarification,
           Route.RESEARCH, verification_level, case_id=case_id, question=message)


def _reply(
    run_id: str,
    thread_id: str,
    text: str | None,
    answer: dict | None,
    clarification: str | None,
    route: Route,
    verification_level: str,
    case_id: str | None = None,
    question: str | None = None,
) -> None:
    """Store the assistant turn and close the run.

    A run that produced nothing writes no message: an empty assistant row
    reads to the next rewrite as an answer that was given, which is the same
    reason the timeout branch stores none.
    """
    with connection() as conn:
        # Re-checked at the last moment: the graph ran to completion, but
        # between its final node and this write the reader may have
        # cancelled or deleted the thread.
        if runs.beat(conn, run_id) != "running":
            log.info("run %s is no longer wanted; discarding its answer", run_id)
            return
        # The right to finish, taken before anything is written and in the
        # same transaction as the writing. A requeued run can be worked by
        # two workers; only one gets past here.
        if not runs.complete(conn, run_id):
            log.info("run %s was already answered elsewhere; discarding", run_id)
            return
        if text or answer:
            add_message(conn, thread_id, "assistant", text or "", answer=answer)
            # A thread in a case leaves its conclusions behind. Without this
            # the case carries documents forward but not findings, and the
            # fourth question re-derives what the first three settled --
            # which is the whole reason the container exists.
            if case_id and answer is not None and question is not None:
                _remember(conn, case_id, question, answer)
        runs.append(conn, run_id, "done", {
            "text": text,
            "answer": answer,
            "clarification_needed": clarification,
            "route": route.value,
            "verification_level": verification_level,
        })


def _answer_from_thread(thread_id: str, user_id: str, message: str):
    """The ANSWER route's reply: `(text, answer)`.

    `answer` is None when the thread held nothing that answers the question,
    which the caller renders as `COULD_NOT_ANSWER` rather than as an answer.

    The connection is released before the composition call. Holding a
    transaction across a model round-trip queues every other writer behind
    it.
    """
    with connection() as conn:
        stored = recent_answers(conn, thread_id, user_id, HISTORY_TURNS)

    composed = answer_from_thread(message, stored)
    if composed is None:
        return COULD_NOT_ANSWER, None
    return render(composed), _as_dict(composed)


def _history(conn, thread_id: str, user_id: str, before_message_id: int) -> list[Turn]:
    """The conversation as it stood before this question was asked.

    The API stores the question and then enqueues, so the rewriter would
    otherwise be handed the very message it is rewriting -- and read it as
    context for itself.
    """
    return [
        Turn(role=message.role, content=message.content)
        for message in recent_turns(conn, thread_id, user_id, HISTORY_TURNS + 1)
        if message.message_id < before_message_id
    ][-HISTORY_TURNS:]


def _already_clarified(history: list[Turn], asked: set[str]) -> bool:
    """Whether this thread has already put a clarifying question.

    Asked once, then proceed whatever came back. The gate re-asks while the
    fact it wants is unset, and an answer it cannot parse -- a district, a
    spelling, a state the table does not carry -- leaves it unset forever.
    Researching without the fact gives a weaker answer; asking a fourth time
    gives none at all.
    """
    return any(
        turn.role == "assistant" and turn.content.strip() in asked for turn in history
    )


def _stop_reason(run_id: str) -> str | None:
    """Why this job should stop, or None to carry on. Beats on the way past.

    One statement answers all three questions, because they are one row: a
    run that is gone was deleted with its thread, a cancelled one has a
    reader who left, and anything still running gets its heartbeat moved so
    the reaper knows a worker owns it.
    """
    with connection() as conn:
        status = runs.beat(conn, run_id)
    if status is None:
        return "the thread was deleted; stopping"
    if status == "cancelled":
        return "cancelled by the reader; stopping"
    return None


def _fail(run_id: str, code: str, message: str) -> None:
    """Close the run with a reason, unless it is already gone.

    A run deleted by its reader is not a failure to record. Trying anyway
    raises a foreign-key violation, which reads in the log exactly like a
    bug and is not one.
    """
    try:
        with connection() as conn:
            if not runs.exists(conn, run_id):
                log.info("run %s was deleted; nothing to fail", run_id)
                return
            runs.fail(conn, run_id, code, message)
    except Exception:
        log.exception("could not record the failure of run %s", run_id)


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
    context, while failing the run costs the user the answer they already
    paid for.
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


# Words per event. Small enough to read as a stream rather than a dump;
# large enough that a 40-word lede is not 40 separate rows.
_CHUNK_WORDS = 4


def _chunk_words(text: str) -> list[str]:
    """`text` split on whitespace into `_CHUNK_WORDS`-word pieces, each
    carrying a trailing space so the client can just concatenate them."""
    words = text.split()
    return [
        " ".join(words[i : i + _CHUNK_WORDS]) + " "
        for i in range(0, len(words), _CHUNK_WORDS)
    ]
