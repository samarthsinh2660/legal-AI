"""Graph nodes.

Nodes are thin. Real work lives in legal_ai.context, legal_ai.retrieval and
(from 7a) legal_ai.agents -- a node's job is to call it and put the result
on the channel.

Analyst, verification and draft are pass-throughs. They exist now so Phases
4-6 fill bodies rather than reshaping the graph, and each carries the
signature its real implementation will keep.

`document` is NOT one of those: it is milestone 6.4, in this phase, because
ThreadContext holds case facts and documents and something has to produce
them.
"""

from __future__ import annotations

from legal_ai.context.builder import build_thread_context
from legal_ai.graph.state import ResearchState


def document(state: ResearchState) -> dict:
    """Extract structure from the case's documents into the channel.

    A separate agent rather than a tool call inside the researcher: a
    300-page petition does not fit a researcher's window and should not,
    because the researcher needs what the document *says*, not the
    document. This agent spends its own window on the raw file and returns
    parties, dates, cited sections and issues -- structure only, never raw
    text. Same isolation pattern as research fan-out.

    Facts supplied on the channel are used as given; that is the path a
    caller who has already extracted them takes, and it keeps the graph
    runnable without an API key. Otherwise each id is read from the
    canonical store and extracted here.

    A document that cannot be read is skipped rather than failing the run:
    one unreadable exhibit in a bundle must not cost the user the whole
    research thread.
    """
    if state.get("document_facts"):
        return {}

    document_ids = state.get("document_ids") or []
    if not document_ids:
        return {}

    from legal_ai.agents.document import extract_document_facts
    from legal_ai.knowledge.static.db import get_connection
    from legal_ai.knowledge.static.store import get_document

    facts = []
    conn = get_connection()
    try:
        for document_id in document_ids:
            stored = get_document(conn, document_id)
            if stored is None or not stored.full_text.strip():
                continue
            facts.append(extract_document_facts(document_id, stored.full_text))
    finally:
        conn.close()
    return {"document_facts": facts}


def context_builder(state: ResearchState) -> dict:
    """Build the ThreadContext once.

    When the thread belongs to a case, it is seeded from what that case has
    already established rather than built from the question alone -- the
    fourth question about a matter should not re-derive what the first
    three settled. See legal_ai.case.session.
    """
    documents = tuple(state.get("document_facts") or [])
    case_id = state.get("case_id")

    if case_id is None:
        return {
            "context": build_thread_context(
                state["question"], case_id=None, documents=documents
            )
        }

    from legal_ai.case.session import start_session
    from legal_ai.knowledge.static.db import get_connection

    conn = get_connection()
    try:
        context = start_session(
            conn, state["question"], case_id=case_id, documents=documents
        )
    finally:
        conn.close()
    return {"context": context}


def clarification(state: ResearchState) -> dict:
    """Ask only when a missing fact would make the research wrong.

    Blocking gaps are enumerated, not guessed. See
    legal_ai.context.clarification.
    """
    from legal_ai.context.clarification import clarification_needed

    context = state.get("context")
    if context is None:
        return {"clarification_needed": None}
    return {"clarification_needed": clarification_needed(context)}


def research(state: ResearchState) -> dict:
    """Supervisor + fan-out to research agents.

    The only stage with discretion, and it decides exactly two things: how
    many angles, and go again or stop. The ThreadContext built upstream is
    passed through unchanged -- no agent re-derives it.
    """
    from legal_ai.agents.supervisor import research as run_research
    from legal_ai.context.serialization import render

    context = state.get("context")
    result = run_research(
        state["question"],
        context=render(context) if context is not None else "",
    )
    return {
        "findings": result.evidence,
        "research_rounds": state.get("research_rounds", 0) + 1,
    }


def analyst(state: ResearchState) -> dict:
    """Turn findings into structured claims, each carrying its Evidence id.

    Pass-through until Phase 5. Structured rather than prose so verification
    is a lookup rather than an LLM re-reading an LLM.
    """
    return {}


def verification(state: ResearchState) -> dict:
    """Groundedness, then coverage.

    Groundedness runs first and uses no model, so it cannot itself
    hallucinate. See legal_ai.verification.
    """
    from legal_ai.knowledge.static.db import get_connection
    from legal_ai.verification.groundedness import check_groundedness

    passes = state.get("verification_passes", 0) + 1
    claims = state.get("claims") or []
    if not claims:
        # Nothing produces claims until the Analyst lands in Phase 5.
        return {"verification_passes": passes, "unsupported_claims": []}

    retrieved = {item.document_id for item in state.get("findings") or [] if item.document_id}
    conn = get_connection()
    try:
        result = check_groundedness(claims, conn, available_ids=retrieved)
    finally:
        conn.close()
    return {"verification_passes": passes, "unsupported_claims": result.unsupported_texts}


def draft(state: ResearchState) -> dict:
    """Render the DraftAnswer the UI contract expects.

    Pass-through until Phase 5.
    """
    return {"answer": f"[stub answer for: {state['question']}]"}
