"""Research a question: plan the angles, search them, summarise.

One or two model calls per question, regardless of how many angles:

    1. plan_research   question -> angles + statutory queries
    2. summarise       ONLY when the findings are too long to hand over as
                       they are -- summarising can only lose detail, so it
                       is not worth a call on a short result

An earlier version made five calls at one angle and thirteen at three --
decompose, then rewrite, plan, assess and compress per angle. Rewrite and
plan produced the same thing (a query) and decompose produced it a third
time, so they are one call now. Assess is gone: with the queries chosen up
front there is nothing for a second round to reconsider that a wider search
would not have caught first.

Control flow is code. The model decides how many angles and how to phrase
the queries -- both ambiguity. It never decides what runs.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import psycopg

from legal_ai.agents.research_plan import Angle, plan_research
from legal_ai.context.models import ThreadContext
from legal_ai.retrieval.case_law import court_filter, section_identifiers, wants_case_law
from legal_ai.agents.validator import validate
from legal_ai.config import DEFAULT_CONFIG
from legal_ai.llm.client import generate
from legal_ai.schemas.evidence import Evidence
from legal_ai.retrieval.hybrid import hybrid_search
from legal_ai.retrieval.metadata import MetadataFilters

SUMMARISE_PROMPT = """Summarise these retrieved Indian legal provisions for
a colleague researching: {question}

{findings}

At most 150 words. State what the provisions say. Do not add law that is not
shown above."""


@dataclass(frozen=True)
class ResearchResult:
    question: str
    angles: list[Angle] = field(default_factory=list)
    evidence: list[Evidence] = field(default_factory=list)
    dropped: list[tuple[str, str]] = field(default_factory=list)

    @property
    def agents_spawned(self) -> int:
        """Angles searched. Tracked as a cost metric -- a lookup question
        staying at 1 is the signal that decomposition is not over-firing."""
        return len(self.angles)


def _search(query: str, limit: int, filters: MetadataFilters | None = None) -> list[Evidence]:
    """One search. No model call.

    Calls hybrid_search directly, at the width it will return. That is
    exactly what the rewrite-only baseline in evals.run does, so a
    single-angle question runs the same code as the best-measured path
    rather than something merely similar -- there is then no difference
    between them left to measure.

    Deliberately not search_statutes: that over-fetches five-fold and then
    filters by document type, which is right for a caller browsing statutes
    and wrong here.
    """
    try:
        return list(hybrid_search(query, limit=limit, filters=filters))
    except Exception:
        return []


def _merge(per_angle: list[list[Evidence]], limit: int) -> list[Evidence]:
    """Combine the angles' results without re-scoring them.

    A single angle is returned in the order search gave it. That order was
    already produced by the full Phase 2 pipeline -- fusion across three
    signals, then a cross-encoder over the shortlist -- and scored against
    the *statutory* query.

    Re-ranking it afterwards against the user's original wording undoes
    that. It scores each passage against "builder failed to give possession
    of my flat", which is the exact vocabulary the statutory query existed
    to get away from. Measured: doing so scored MRR 0.542 where leaving the
    order alone scores what plain rewrite-then-search scores.

    Several angles are interleaved by position, so each angle's best hit
    sits near the top and no angle is buried under another's tail.
    """
    if len(per_angle) == 1:
        # One angle, one list, already ranked by the full Phase 2 pipeline
        # against the statutory query. Nothing to merge.
        return per_angle[0][:limit]

    merged: list[Evidence] = []
    seen: set[str] = set()
    for position in range(max((len(a) for a in per_angle), default=0)):
        for angle_results in per_angle:
            if position >= len(angle_results):
                continue
            item = angle_results[position]
            if item.document_id in seen:
                continue
            seen.add(item.document_id)
            merged.append(item)
    return merged[:limit]


def summarise(question: str, evidence: list[Evidence]) -> str:
    """Findings for the caller, summarised only when they are too long.

    Below `summarise_above_chars` the provisions are handed over as they
    are: a model call there costs latency and quota to *lose* detail, since
    the titles and passages already say what a reader needs. The threshold
    is the point where a list stops being readable at a glance.

    When a summary is made, the Evidence ids are appended structurally
    rather than asked for. A summary that loses them makes every downstream
    claim ungroundable, and that must not depend on a model complying.
    """
    if not evidence:
        return "No supporting provisions were retrieved."

    rendered = "\n\n".join(
        f"[{item.document_id}] {item.title or ''}\n{item.content[:600]}" for item in evidence
    )
    ids = ", ".join(item.document_id for item in evidence if item.document_id)

    if len(rendered) <= DEFAULT_CONFIG.summarise_above_chars:
        return f"{rendered}\n\nSources: {ids}"

    try:
        text = generate(
            SUMMARISE_PROMPT.format(question=question, findings=rendered),
            max_output_tokens=DEFAULT_CONFIG.summary_model_max_tokens,
        )
    except Exception:
        text = f"Retrieved {len(evidence)} provisions."
    return f"{text.strip()}\n\nSources: {ids}"


def research(
    question: str,
    context: str = "",
    max_angles: int = DEFAULT_CONFIG.max_concurrent_research_units,
    limit: int = DEFAULT_CONFIG.limit_per_angle,
    conn: psycopg.Connection | None = None,
    chain: tuple[str, ...] | None = None,
    thread_context: ThreadContext | None = None,
    discover_cases: bool | None = None,
) -> ResearchResult:
    """Plan, search every angle, validate, rank, summarise.

    `chain` pins the model, for benchmark runs that must not slide down the
    fallback chain midway and blend two models into one score.

    `thread_context` supplies the jurisdiction to filter on. Phase 2 shipped
    those filters and Phase 3 built the context that implies them, and
    nothing passed one to the other -- so naming a court did nothing until
    now.

    `discover_cases` overrides the deterministic gate. Left None, judgments
    are fetched only for a question that asks for them: discovery reaches a
    third party, and paying that on every statute lookup would cost every
    user seconds for an answer they did not ask for.
    """
    angles = plan_research(question, context=context, max_angles=max_angles, chain=chain)
    # No angles means the planner found no legal issue to research. Stop
    # here rather than searching, and in particular before `_discover`,
    # which reaches a third party.
    if not angles:
        return ResearchResult(question=question)

    filters = _filters_for(thread_context)

    per_angle: list[list[Evidence]] = []
    dropped: list[tuple[str, str]] = []
    for angle in angles:
        result = validate(_search(angle.query, limit=limit, filters=filters), conn=conn)
        dropped.extend(result.dropped)
        per_angle.append(result.kept)

    ranked = _merge(per_angle, limit=limit)

    judgments: list[Evidence] = []
    if discover_cases if discover_cases is not None else wants_case_law(question):
        judgments = _discover(question, ranked, thread_context, conn)

    evidence = ranked + [j for j in judgments if j.document_id not in
                         {e.document_id for e in ranked}]
    return ResearchResult(
        question=question,
        angles=angles,
        # No summary: the Analyst writes the answer from the Evidence, and
        # nothing read this one. It cost 60.3s of a 233s turn.
        # `summarise()` stays for a caller that wants prose.
        evidence=evidence,
        dropped=dropped,
    )


def _filters_for(thread_context: ThreadContext | None) -> MetadataFilters | None:
    """Retrieval filters the thread context implies, or None.

    Not applied when the context names a court: `documents.court` is only
    populated on judgments, so filtering statutes by it would return
    nothing. Jurisdiction narrows case law, and case law is discovered
    through its own path.
    """
    if thread_context is None:
        return None
    from legal_ai.context.builder import to_filters

    filters = to_filters(thread_context)
    if filters.decision_date_from is None and filters.decision_date_to is None:
        return None
    return MetadataFilters(
        decision_date_from=filters.decision_date_from,
        decision_date_to=filters.decision_date_to,
    )


def _discover(
    question: str,
    statutes: list[Evidence],
    thread_context: ThreadContext | None,
    conn: psycopg.Connection | None,
) -> list[Evidence]:
    """Judgments for a question that names no case.

    The provisions just retrieved become the second query. A section number
    is what a judgment quotes, so it is a far stronger handle on case law
    than the user's own wording -- and it is grounded, unlike a phrase the
    model recalled.
    """
    from legal_ai.knowledge.static.db import get_connection
    from legal_ai.tools.judgments import discover_judgments

    owns_connection = conn is None
    connection = conn or get_connection()
    try:
        section_queries = section_identifiers(statutes, connection)
    except Exception:
        section_queries = []
    finally:
        if owns_connection:
            connection.close()

    try:
        return discover_judgments(
            question,
            section_queries=section_queries,
            court=court_filter(question, thread_context),
            limit=DEFAULT_CONFIG.judgment_search_limit,
        )
    except Exception:
        # Discovery is additive. A third party being down must not cost
        # the caller the statutes that were already found.
        return []
