"""The join between a case and the research sessions inside it.

Phase 4 §3 requires both entry points to work:

    Flow A   research first, attach to a case afterwards
    Flow B   create the case, then research inside it

They are the same two operations in opposite order -- seed a thread from a
case, and write a session's results back -- so both live here rather than
being reimplemented at each entry point.
"""

from __future__ import annotations

from dataclasses import replace

import psycopg

from legal_ai.case.store import get_case, record_finding, record_session
from legal_ai.context.builder import attach_case, build_thread_context
from legal_ai.context.models import DocumentFacts, EstablishedFinding, ThreadContext
from legal_ai.schemas.evidence import Evidence


def start_session(
    conn: psycopg.Connection,
    question: str,
    case_id: str | None = None,
    documents: tuple[DocumentFacts, ...] = (),
) -> ThreadContext:
    """The ThreadContext a new research thread starts from.

    With no case this is exactly Phase 3's behaviour -- a thread may belong
    to no case at all, and a plain question of law must not require the user
    to invent a matter first.

    With a case, the thread starts from what that case already established.
    That is the whole point of the container: the fourth question about a
    matter should not re-derive what the first three settled.

    An unknown case_id is not fatal -- the thread runs uncontextualised
    rather than failing, since losing the seed degrades an answer while
    refusing to research loses it entirely.
    """
    context = build_thread_context(question, case_id=case_id, documents=documents)
    if case_id is None:
        return context

    case = get_case(conn, case_id)
    if case is None:
        return context

    seeded = attach_case(context, case_id, case_findings=case.findings)
    # The description is what the New Case modal tells the user is seeding
    # the agents. Leaving it in the database would make that label a lie.
    seeded = replace(seeded, case_description=case.description)
    seeded = _inherit_jurisdiction(seeded, case)
    record_session(conn, case_id, question)
    return seeded


def _inherit_jurisdiction(context: ThreadContext, case) -> ThreadContext:
    """Fill state and court from the case where the question left them unset.

    The question wins: a Karnataka question inside a Maharashtra matter is a
    Karnataka question. Nothing is inferred from the description or the
    court name -- an unknown state stays unknown so
    `context.clarification` can ask rather than guess.

    Without this, a matter recorded as Maharashtra RERA still produced a
    thread with no state and every state-dependent question stopped to ask.
    """
    jurisdiction = context.jurisdiction
    state = jurisdiction.state or case.state
    court = jurisdiction.court or case.court
    if state == jurisdiction.state and court == jurisdiction.court:
        return context
    return replace(
        context, jurisdiction=replace(jurisdiction, state=state, court=court)
    )


def save_to_case(
    conn: psycopg.Connection,
    case_id: str,
    question: str,
    findings: tuple[EstablishedFinding, ...] = (),
    evidence: list[Evidence] | None = None,
) -> None:
    """Attach a finished research session to a case (Flow A).

    `findings` are what the session settled. When none are given, the
    session's evidence is recorded as a single finding answering the
    question asked -- so "Save to case" always leaves a trace of what was
    researched, rather than silently recording nothing.

    Evidence ids are carried, never the evidence text: a finding must stay
    checkable against the corpus, and copying passages into the case would
    let the two drift apart the moment a provision is amended.
    """
    record_session(conn, case_id, question)

    if not findings and evidence:
        findings = (
            EstablishedFinding(
                claim=question,
                evidence_ids=tuple(e.document_id for e in evidence if e.document_id),
                source_case_id=case_id,
            ),
        )

    for finding in findings:
        record_finding(conn, case_id, finding)
