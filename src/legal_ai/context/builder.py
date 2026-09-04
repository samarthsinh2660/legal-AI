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

# Every state and union territory, with the High Court a matter there is
# normally heard in. Several courts serve more than one region, which is why
# this is a table and not a suffix rule.
#
# It was eight entries until 2026-09-04, and the twenty missing states were
# not a degraded answer but a dead end: the clarification gate asks "which
# state is this in?" for anything state-wise (rent, mutation, stamp duty),
# and re-asks while `jurisdiction.state` is unset. A user in Uttarakhand
# answering correctly, every time, was asked again forever. Reported from
# the live deploy. The earlier QA pass had cleared this gate after testing
# Maharashtra, which is one of the eight that worked.
_STATE_COURTS: dict[str, str] = {
    "andhra pradesh": "Andhra Pradesh High Court",
    "arunachal pradesh": "Gauhati High Court",
    "assam": "Gauhati High Court",
    "bihar": "Patna High Court",
    "chhattisgarh": "Chhattisgarh High Court",
    "goa": "Bombay High Court",
    "gujarat": "Gujarat High Court",
    "haryana": "Punjab and Haryana High Court",
    "himachal pradesh": "Himachal Pradesh High Court",
    "jharkhand": "Jharkhand High Court",
    "karnataka": "Karnataka High Court",
    "kerala": "Kerala High Court",
    "madhya pradesh": "Madhya Pradesh High Court",
    "maharashtra": "Bombay High Court",
    "manipur": "Manipur High Court",
    "meghalaya": "Meghalaya High Court",
    "mizoram": "Gauhati High Court",
    "nagaland": "Gauhati High Court",
    "odisha": "Orissa High Court",
    "punjab": "Punjab and Haryana High Court",
    "rajasthan": "Rajasthan High Court",
    "sikkim": "Sikkim High Court",
    "tamil nadu": "Madras High Court",
    "telangana": "Telangana High Court",
    "tripura": "Tripura High Court",
    "uttar pradesh": "Allahabad High Court",
    "uttarakhand": "Uttarakhand High Court",
    "west bengal": "Calcutta High Court",
    # Union territories.
    "andaman and nicobar": "Calcutta High Court",
    "chandigarh": "Punjab and Haryana High Court",
    "dadra and nagar haveli": "Bombay High Court",
    "daman and diu": "Bombay High Court",
    "delhi": "Delhi High Court",
    "jammu and kashmir": "High Court of Jammu & Kashmir and Ladakh",
    "ladakh": "High Court of Jammu & Kashmir and Ladakh",
    "lakshadweep": "Kerala High Court",
    "puducherry": "Madras High Court",
    # Former names, still what people type.
    "orissa": "Orissa High Court",
    "pondicherry": "Madras High Court",
    "uttaranchal": "Uttarakhand High Court",
}

# Longest first, so "uttar pradesh" cannot be shadowed by a shorter name
# that happens to sit earlier, and on word boundaries, so "goa" does not
# match inside "Goalpara".
_STATE_PATTERN = re.compile(
    r"\b(" + "|".join(
        re.escape(name) for name in sorted(_STATE_COURTS, key=len, reverse=True)
    ) + r")\b",
    re.IGNORECASE,
)

# Phrases that ask for the position as it stands now rather than at some
# past date. See ThreadContext.needs_current_law.
_CURRENT_LAW = re.compile(
    r"\b(current(ly)?|latest|as of today|today|still good law|"
    r"still valid|recent(ly)?|now)\b",
    re.IGNORECASE,
)


def _display(state: str) -> str:
    """The state's name as it is written -- "Jammu and Kashmir", not "And"."""
    return " ".join(
        word if word == "and" else word.title() for word in state.split()
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
    found = _STATE_PATTERN.search(haystack)
    state = found.group(1) if found else None

    return ThreadContext(
        question=question.strip(),
        case_id=case_id,
        documents=tuple(documents),
        document_ids=tuple(d.document_id for d in documents),
        jurisdiction=Jurisdiction(
            court=_STATE_COURTS[state] if state else None,
            state=_display(state) if state else None,
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
