"""The case graph's channel.

Separate from ResearchState because the two graphs answer different
questions. A research thread runs once per question and ends; a case is a
workspace that is opened, added to, and opened again. Sharing one state
would force every research run to carry case fields it never sets, and
every case view to carry a question it does not have.
"""

from __future__ import annotations

from typing import Optional, TypedDict

from legal_ai.case.models import Case, CaseAnalysis
from legal_ai.context.models import DocumentFacts
from legal_ai.schemas.evidence import Evidence


class CaseState(TypedDict, total=False):
    case_id: str

    # Loaded from the store. None when the case_id is unknown, which ends
    # the run rather than analysing an empty container.
    case: Optional[Case]

    # Read from storage where a document has been read before, extracted
    # here where it has not. Extraction costs a model call per window, so
    # a case is read once and viewed many times.
    documents: list[DocumentFacts]

    # What this case's research sessions retrieved. Supplied by the caller;
    # the case graph does not research on its own, because a case analysis
    # is a view of what is known, not a new question.
    evidence: list[Evidence]

    analysis: Optional[CaseAnalysis]

    # Set when the case_id does not exist. Ends the run with a reason
    # rather than returning an empty analysis that looks like a real one.
    error: Optional[str]
