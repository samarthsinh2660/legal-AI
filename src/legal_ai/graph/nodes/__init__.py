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
    from legal_ai.case.files import get_case_file_text
    from legal_ai.knowledge.static.db import get_connection

    facts = []
    conn = get_connection()
    try:
        for document_id in document_ids:
            # Read from case_files, not `documents`: an uploaded pleading is
            # the client's, not corpus, and is deliberately kept out of the
            # table hybrid_search reads. See legal_ai.case.files.
            text = get_case_file_text(conn, document_id)
            if not text or not text.strip():
                continue
            facts.append(extract_document_facts(document_id, text))
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
        thread_context=context,
    )
    return {
        "findings": result.evidence,
        "searched": bool(result.angles),
        "research_rounds": state.get("research_rounds", 0) + 1,
    }


def analyst(state: ResearchState) -> dict:
    """Turn findings into structured claims, each carrying its Evidence ids.

    Structured rather than prose so verification is a lookup rather than an
    LLM re-reading an LLM. Until this node did real work the verifier had
    nothing to check and returned early on every run.

    This replaces the supervisor's summarise call rather than adding to it,
    so a question still costs one model call here.
    """
    from legal_ai.agents.analyst import analyse

    context = state.get("context")
    result = analyse(
        state["question"],
        list(state.get("findings") or []),
        documents=tuple(context.documents) if context is not None else (),
        searched=state.get("searched", True),
    )
    return {"claims": list(result.claims), "analysis": result}


def verification(state: ResearchState) -> dict:
    """Run the verification funnel over the Analyst's claims.

    Deterministic stages always run; the Verification Agent runs only when
    the reader asked for it (`verification_level`). See
    legal_ai.verification.pipeline for the stage order and why it is that
    order.

    `unsupported_claims` carries only claims we have a *finding against* --
    never claims we merely could not check. Re-researching a claim whose
    evidence contradicts it can help; re-researching one whose evidence we
    do not hold cannot, and looping on it would spend passes to no purpose.
    """
    from legal_ai.config import DEFAULT_CONFIG
    from legal_ai.knowledge.static.db import get_connection
    from legal_ai.verification.pipeline import verify

    passes = state.get("verification_passes", 0) + 1
    claims = state.get("claims") or []
    if not claims:
        return {"verification_passes": passes, "unsupported_claims": [],
                "verification_report": None}

    level = state.get("verification_level") or DEFAULT_CONFIG.verification_level
    retrieved = {item.document_id for item in state.get("findings") or [] if item.document_id}

    conn = get_connection()
    try:
        report = verify(
            claims, conn, available_ids=retrieved, use_model=(level == "verified")
        )
    finally:
        conn.close()

    return {
        "verification_passes": passes,
        "unsupported_claims": report.needs_research,
        "verification_report": report,
    }


def draft(state: ResearchState) -> dict:
    """Assemble the DraftAnswer the UI contract expects.

    Deterministic -- no model call. Its inputs are already structured, and
    re-rendering them through a model would only risk dropping a citation.

    This is where the verifier becomes visible: claims it could not ground
    are moved into `needs_verification` rather than deleted, so a reader can
    tell a short answer from an incomplete one.
    """
    from legal_ai.agents.draft import build_answer, render
    from legal_ai.config.settings import Configuration
    from legal_ai.graphdb.client import get_driver
    from legal_ai.knowledge.static.db import get_connection
    from legal_ai.retrieval.authority import authority_lookup
    from legal_ai.schemas.answer import AnalysisResult

    analysis = state.get("analysis") or AnalysisResult()
    findings = list(state.get("findings") or [])

    # Judgments reach the reader strongest first rather than in id order.
    # Off leaves them in id order, which is what shipped before Phase 7.
    # A graph that is down must not cost the user their answer either, so a
    # failed lookup falls back the same way.
    authority = {}
    judgment_ids = [
        item.document_id for item in findings
        if item.document_id and (item.document_type or "") == "judgment"
    ]
    if judgment_ids and Configuration.from_env().rank_by_authority:
        try:
            driver = get_driver()
            conn = get_connection()
            try:
                authority = authority_lookup(driver, conn, judgment_ids)
            finally:
                conn.close()
                driver.close()
        except Exception:
            authority = {}

    answer = build_answer(
        state["question"],
        analysis,
        findings,
        unsupported=tuple(state.get("unsupported_claims") or []),
        authority=authority,
        report=state.get("verification_report"),
    )
    return {"answer": render(answer), "draft_answer": answer}
