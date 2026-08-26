"""Assemble a verified analysis into the answer the UI renders.

Not an agent and not a model call. Its inputs are already structured --
claims with ids, Evidence with types -- so this is assembly. Handing
structured data to a model to re-render it would only give it a chance to
drop a citation.

Its one real job is making the verifier's result visible. Groundedness runs
over the claims and separates what is supported from what is not; without
this step both would reach the reader as the same paragraph, in the same
font, with the same apparent confidence. Labelling the difference is the
whole payoff for having a verifier at all.
"""

from __future__ import annotations

from legal_ai.schemas.answer import AnalysisResult, DraftAnswer
from legal_ai.schemas.evidence import Evidence
from legal_ai.schemas.verification import Claim

_STATUTE_TYPES = frozenset({"act", "section"})


def build_answer(
    question: str,
    analysis: AnalysisResult,
    evidence: list[Evidence],
    unsupported: tuple[str, ...] = (),
) -> DraftAnswer:
    """The DraftAnswer for this question.

    `unsupported` is the verifier's output -- claim texts it could not
    ground. Those claims are moved out of `key_elements` and into
    `needs_verification` rather than deleted: a reader who cannot see that
    something was dropped cannot tell a short answer from an incomplete
    one.
    """
    unsupported_set = set(unsupported)
    supported: list[Claim] = []
    flagged: list[str] = []
    for claim in analysis.claims:
        # A claim citing nothing is unsupported whether or not the verifier
        # ran -- there is nothing for it to have checked.
        if claim.text in unsupported_set or not claim.evidence_ids:
            flagged.append(claim.text)
        else:
            supported.append(claim)

    cited = {i for claim in supported for i in claim.evidence_ids}
    by_id = {item.document_id: item for item in evidence if item.document_id}

    statutes = [i for i in cited if (by_id.get(i) and (by_id[i].document_type or "") in _STATUTE_TYPES)]
    judgments = [i for i in cited if (by_id.get(i) and (by_id[i].document_type or "") == "judgment")]

    return DraftAnswer(
        question=question,
        lede=analysis.lede,
        key_elements=tuple(supported),
        applicable_law=tuple(sorted(statutes)),
        key_judgments=tuple(sorted(judgments)),
        needs_verification=tuple(flagged),
        citations=tuple(sorted(cited)),
    )


def render(answer: DraftAnswer) -> str:
    """Plain-text rendering, for a caller with no UI -- scripts, the CLI,
    and the `answer` string the graph has always returned."""
    lines = [answer.lede] if answer.lede else []

    if answer.key_elements:
        lines.append("")
        for claim in answer.key_elements:
            lines.append(f"- {claim.text} [{', '.join(claim.evidence_ids)}]")

    if answer.needs_verification:
        lines.append("")
        lines.append("Could not be verified against the retrieved sources:")
        for text in answer.needs_verification:
            lines.append(f"- {text}")

    if answer.citations:
        lines.append("")
        lines.append("Sources: " + ", ".join(answer.citations))

    lines.append("")
    lines.append(answer.disclaimer)
    return "\n".join(lines)
