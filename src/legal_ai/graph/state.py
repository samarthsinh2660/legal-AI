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

    # Whether this thread has already asked one. The gate asks once and then
    # researches with whatever it has, since an answer it cannot parse would
    # otherwise leave it asking the same question forever.
    clarification_asked: bool

    # Whether any angle was planned. False means the planner found no legal
    # issue, so nothing was searched -- which the Analyst must not report as
    # an empty corpus.
    searched: bool

    # Structured claims from the Analyst, each carrying its Evidence ids.
    # Verification is vacuous without them, which is what it was until the
    # Analyst landed.
    claims: list

    # The Analyst's full result -- claims plus the lede. Carried separately
    # so the draft node does not have to re-derive prose from claims.
    analysis: Optional[object]

    # The assembled DraftAnswer. `answer` stays a string for callers that
    # only want text; this is the structure the UI renders.
    draft_answer: Optional[object]

    # Claims verification could not ground. A non-empty value sends the run
    # back for bounded re-research, up to GraphConfig.max_verification_passes.
    unsupported_claims: list[str]

    answer: Optional[str]

    # Bounded by graph.configuration; the loop terminates on these, never on
    # the model choosing to stop.
    research_rounds: int
    verification_passes: int

    # What the reader asked for: "quick" or "verified". On the state rather
    # than read from config inside the node so one thread can be checked
    # harder than another without changing a global.
    verification_level: str

    # The full per-claim outcome, for the answer to annotate from. Distinct
    # from unsupported_claims, which is only what the loop-back acts on.
    verification_report: object
