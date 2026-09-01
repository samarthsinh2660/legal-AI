"""Thread context -- what every node in a research thread is initialised from.

Implements docs/AI_PROJECT_PROPOSAL.md §6. Built once per thread and passed
read-only, so the question is analysed once rather than re-derived by each
node at N times the token cost and with N chances to disagree.

Everything here is frozen. A change produces a new revision rather than a
mutation, which is what makes a thread reproducible after the fact.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass(frozen=True)
class Jurisdiction:
    """Where the matter sits. `state` is separate from `court` because
    several statutes are state-wise (RERA rules, rent, stamp duty) even
    when no particular court is in play yet."""

    court: str | None = None
    state: str | None = None


@dataclass(frozen=True)
class EstablishedFinding:
    """Something the thread has settled, with the evidence that settled it.

    `depends_on` names the context fields the finding rests on. When one of
    those fields changes, the finding is dropped rather than silently
    carried into a matter it was never true for -- a holding on Gujarat law
    does not survive the jurisdiction changing to Maharashtra.
    """

    claim: str
    evidence_ids: tuple[str, ...]
    depends_on: tuple[str, ...] = ()
    source_case_id: str | None = None


@dataclass(frozen=True)
class DocumentFacts:
    """What the Document Agent extracted from one uploaded file.

    Structure only. The document body never travels with this -- a 300-page
    petition would not fit in a researcher's context window, and the
    researcher needs what the document *says*, not the document.
    """

    document_id: str
    document_type: str | None = None
    parties: tuple[str, ...] = ()
    dates: tuple[str, ...] = ()
    cited_sections: tuple[str, ...] = ()
    issues: tuple[str, ...] = ()

    # Operative terms of an agreement or notice -- the possession date, the
    # payment schedule, the penalty, the termination right. Separate from
    # `issues` because a clause is what the document *says*, while an issue
    # is what it puts in dispute, and the clause is usually what decides it.
    clauses: tuple[str, ...] = ()

    # What each party asserts. The direct input to the Analyst Agent in
    # Phase 5, kept distinct from `issues` for the same reason: "the
    # promoter says the delay was force majeure" is a contention, not a
    # question for the court.
    claims: tuple[str, ...] = ()

    # True when no window of the document reached a model. Without this an
    # upstream outage is indistinguishable from a document that genuinely
    # names no parties: both arrive as empty tuples, and a case view would
    # report "no parties found" when the truth is "we never looked".
    # `cited_sections` is unaffected either way -- it is regex, not model.
    extraction_failed: bool = False


@dataclass(frozen=True)
class ThreadContext:
    question: str
    revision: int = 1

    jurisdiction: Jurisdiction = field(default_factory=Jurisdiction)
    relevant_date_from: date | None = None
    relevant_date_to: date | None = None

    # Set when the question asks for the position *now* -- "current",
    # "latest", "still good law". Retrieval then bypasses the cache, since a
    # stored judgment since overruled is a wrong answer stated confidently.
    needs_current_law: bool = False

    # Optional and settable at any point. A thread may belong to no case at
    # all (a student reading a doctrine), and per design/UX_FLOWS.md a chat
    # can be attached to a case later via "Save to case".
    case_id: str | None = None

    # The matter's own description, when the thread belongs to one.
    # design/UX_FLOWS.md labels this field as seeding the context every agent
    # starts from, so it is carried here rather than left in the database
    # where no agent would see it.
    case_description: str | None = None

    document_ids: tuple[str, ...] = ()
    documents: tuple[DocumentFacts, ...] = ()
    established_findings: tuple[EstablishedFinding, ...] = ()
