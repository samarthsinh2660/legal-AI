"""Build and revise a ThreadContext.

Extraction here is deliberately deterministic -- keyword matching, no model
call. It is cheap, testable without an API key, and good enough for the
three things Phase 3 needs from it: which state, whether the question wants
the law as it stands now, and which court binds. If measurement later shows
a model does better, it can replace the internals without changing callers.
"""

from __future__ import annotations

import re
from dataclasses import replace

from legal_ai.case.timeline import parse_date
from legal_ai.context.models import (
    DocumentFacts,
    EstablishedFinding,
    Jurisdiction,
    ThreadContext,
)
from legal_ai.retrieval.metadata import MetadataFilters

# States whose High Court a matter would normally be heard in. Not
# exhaustive -- it covers what the corpus can currently answer for, and an
# unmatched state simply leaves jurisdiction unset rather than guessing.
_STATE_COURTS: dict[str, str] = {
    "gujarat": "Gujarat High Court",
    "maharashtra": "Bombay High Court",
    "delhi": "Delhi High Court",
    "karnataka": "Karnataka High Court",
    "tamil nadu": "Madras High Court",
    "west bengal": "Calcutta High Court",
    "rajasthan": "Rajasthan High Court",
    "kerala": "Kerala High Court",
}

# Phrases that ask for the position as it stands now rather than at some
# past date. See ThreadContext.needs_current_law.
_CURRENT_LAW = re.compile(
    r"\b(current(ly)?|latest|as of today|today|still good law|"
    r"still valid|recent(ly)?|now)\b",
    re.IGNORECASE,
)


def build_thread_context(
    question: str,
    case_id: str | None = None,
    documents: tuple[DocumentFacts, ...] = (),
) -> ThreadContext:
    """Build the context once, at the start of a thread.

    `documents` is what the Document Agent extracted -- structure, never the
    document body. A document naming a state settles jurisdiction even when
    the question itself does not, which is the common case: people describe
    a grievance without saying where they are.
    """
    haystack = " ".join([question] + [_document_text(d) for d in documents]).lower()
    state = next((name for name in _STATE_COURTS if name in haystack), None)

    return ThreadContext(
        question=question.strip(),
        case_id=case_id,
        documents=tuple(documents),
        document_ids=tuple(d.document_id for d in documents),
        jurisdiction=Jurisdiction(
            court=_STATE_COURTS[state] if state else None,
            state=state.title() if state else None,
        ),
        needs_current_law=bool(_CURRENT_LAW.search(question)),
        # rewrite_question folds a follow-up's date into a self-contained
        # question, the same way it folds a state name in. Reuses
        # case.timeline.parse_date rather than a new regex.
        relevant_date_from=parse_date(question),
    )


def _document_text(facts: DocumentFacts) -> str:
    """The extracted fields as one searchable string, for jurisdiction
    detection. Never includes the document body -- there isn't one here."""
    return " ".join(facts.parties + facts.issues + facts.cited_sections)


def to_filters(context: ThreadContext, document_type: str | None = None) -> MetadataFilters:
    """The retrieval filters this context implies.

    Phase 2 shipped these fields and nothing populated them; this is where
    jurisdiction and the relevant period start constraining what comes back.
    """
    return MetadataFilters(
        document_type=document_type,
        court=context.jurisdiction.court,
        decision_date_from=context.relevant_date_from,
        decision_date_to=context.relevant_date_to,
    )


def revise(context: ThreadContext, **changes) -> ThreadContext:
    """Apply field changes, bump the revision, and drop findings that
    depended on anything that changed.

    Rule 7 of §6: correcting a fact or changing jurisdiction invalidates
    what was concluded under the old value. Dropping is deliberate -- a
    stale finding presented as established is worse than re-researching.
    """
    changed = {
        name for name, value in changes.items() if getattr(context, name) != value
    }
    if not changed:
        return context

    surviving = tuple(
        finding
        for finding in context.established_findings
        if not (set(finding.depends_on) & changed)
    )
    return replace(
        context,
        **changes,
        revision=context.revision + 1,
        established_findings=surviving,
    )


def promote_finding(context: ThreadContext, finding: EstablishedFinding) -> ThreadContext:
    """Record a finding as established. Produces a new revision so the
    thread's history stays reconstructable."""
    return replace(
        context,
        revision=context.revision + 1,
        established_findings=context.established_findings + (finding,),
    )


def attach_case(
    context: ThreadContext,
    case_id: str,
    case_findings: tuple[EstablishedFinding, ...] = (),
) -> ThreadContext:
    """Bind an unattached thread to a case, seeding it with what that case
    already established.

    Per design/UX_FLOWS.md a thread starts caseless and may be attached at
    any point. Attaching is a revision: the case's findings come in, and any
    thread finding that depended on `case_id` is re-derived rather than
    assumed to still hold.
    """
    revised = revise(context, case_id=case_id)
    existing = {(f.claim, f.evidence_ids) for f in revised.established_findings}
    incoming = tuple(f for f in case_findings if (f.claim, f.evidence_ids) not in existing)
    return replace(revised, established_findings=revised.established_findings + incoming)
