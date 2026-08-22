"""The graph's shared channel.

`context` is the ThreadContext from §6 -- built once by the context_builder
node and read by everything downstream. Nodes return only the keys they
change; LangGraph merges the rest.

`findings` accumulates across parallel research agents, so it is reduced by
concatenation rather than replacement -- without that, agents racing to
write the same key would silently drop each other's results.
"""

from __future__ import annotations

import operator
from typing import Annotated, Optional, TypedDict

from legal_ai.context.models import DocumentFacts, ThreadContext
from legal_ai.schemas.evidence import Evidence


class ResearchState(TypedDict, total=False):
    question: str
    case_id: Optional[str]
    document_ids: list[str]

    # Structure extracted by the Document Agent, before the context exists.
    document_facts: list[DocumentFacts]

    context: Optional[ThreadContext]

    # Written by parallel research agents; concatenated, never overwritten.
    findings: Annotated[list[Evidence], operator.add]

    # Set when the clarification gate needs an answer before research can
    # sensibly start. A non-empty value halts the run for the user.
    clarification_needed: Optional[str]

    # Structured claims from the Analyst, each carrying its Evidence ids.
    # Empty until Phase 5; verification is vacuous without them.
    claims: list

    # Claims verification could not ground. A non-empty value sends the run
    # back for bounded re-research, up to GraphConfig.max_verification_passes.
    unsupported_claims: list[str]

    answer: Optional[str]

    # Bounded by graph.configuration; the loop terminates on these, never on
    # the model choosing to stop.
    research_rounds: int
    verification_passes: int
