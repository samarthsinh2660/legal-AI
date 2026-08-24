"""A case: the persistent workspace one real legal matter accumulates in.

A research session (Phase 3) answers one question and ends. A case outlives
every session in it -- documents, parties, a timeline, issues, and the
findings those sessions established. That difference is why this is not a
node in the research graph: the graph runs per question, and a case is what
many of those runs write into.

Everything here is frozen, matching legal_ai.context.models. State changes
go through legal_ai.case.store, which is the only thing that writes.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from legal_ai.context.models import EstablishedFinding


@dataclass(frozen=True)
class TimelineEntry:
    """One dated event, traced to the document that evidences it.

    `parsed` is None when the date could not be read as a calendar date.
    Such an entry is kept rather than dropped: "on the following Monday"
    is a real event a lawyer must see, and silently discarding it would
    make the timeline look complete when it is not. `raw` always holds the
    text as the document wrote it, so nothing is paraphrased into fact.
    """

    raw: str
    document_id: str
    parsed: date | None = None

    @property
    def is_dated(self) -> bool:
        return self.parsed is not None


@dataclass(frozen=True)
class Case:
    """The container. Holds no legal reasoning -- that is CaseAnalysis."""

    case_id: str
    title: str

    court: str | None = None
    state: str | None = None
    case_number: str | None = None
    parties: tuple[str, ...] = ()

    document_ids: tuple[str, ...] = ()

    # Findings promoted from research sessions. These seed the ThreadContext
    # of every later session on this case, which is what stops the same
    # ground being re-researched question after question.
    findings: tuple[EstablishedFinding, ...] = ()

    # Questions researched against this case, oldest first. Kept as the
    # case's own record of what has been asked.
    research_questions: tuple[str, ...] = ()

    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True)
class CaseAnalysis:
    """What the Case Agent concludes about a matter.

    Separate from Case because a Case is durable state and an analysis is a
    derived view: re-running it after a new document must not silently
    rewrite the record of what was uploaded.
    """

    case_id: str
    timeline: tuple[TimelineEntry, ...] = ()
    facts: tuple[str, ...] = ()
    issues: tuple[str, ...] = ()

    # Evidence ids, not prose -- an applicable provision the user cannot
    # open is not usable, and ids keep it checkable.
    applicable_law: tuple[str, ...] = ()
    precedents: tuple[str, ...] = ()

    # The output with no counterpart in a research session: what the matter
    # would need and does not have.
    missing_facts: tuple[str, ...] = ()

    # Places the case's own documents disagree with each other. Only ever
    # populated when the case holds more than one document -- a conflict
    # needs two sides, and one document cannot contradict itself in a way
    # this could point at.
    contradictions: tuple[str, ...] = ()
