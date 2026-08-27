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
from legal_ai.schemas.verification import Claim, Verdict

_STATUTE_TYPES = frozenset({"act", "section"})


def build_answer(
    question: str,
    analysis: AnalysisResult,
    evidence: list[Evidence],
    unsupported: tuple[str, ...] = (),
    report=None,
) -> DraftAnswer:
    """The DraftAnswer for this question.

    `report` is the VerificationReport, and it carries the distinction that
    matters: a claim the evidence contradicts and a claim we never checked
    are different things, and rendering them the same tells a lawyer we
    looked when we did not.

    `unsupported` remains for callers that have only the texts. It is
    treated as a finding against the claim, which is what it always meant.

    Nothing is deleted. A claim that fails any check is moved out of
    `key_elements` and labelled, because a reader who cannot see that
    something was dropped cannot tell a short answer from an incomplete one.
    """
    by_text: dict[str, Verdict] = {}
    if report is not None:
        by_text = {v.claim.text: v.verdict for v in report.verdicts}

    unsupported_set = set(unsupported)
    supported: list[Claim] = []
    flagged: list[str] = []
    unchecked: list[str] = []
    partial: list[str] = []

    for claim in analysis.claims:
        verdict = by_text.get(claim.text)

        # A claim citing nothing has nothing for a verifier to have
        # checked, so it is unsupported whether or not one ran.
        if not claim.evidence_ids or claim.text in unsupported_set:
            flagged.append(claim.text)
        elif verdict is Verdict.UNSUPPORTED:
            flagged.append(claim.text)
        elif verdict is Verdict.PARTIALLY_SUPPORTED:
            partial.append(claim.text)
        elif verdict is Verdict.INSUFFICIENT_EVIDENCE:
            unchecked.append(claim.text)
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
        unchecked=tuple(unchecked),
        partially_supported=tuple(partial),
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

    if answer.partially_supported:
        lines.append("")
        lines.append("Supported only in part by the cited sources "
                     "(the source is narrower than the statement):")
        for text in answer.partially_supported:
            lines.append(f"- {text}")

    if answer.needs_verification:
        lines.append("")
        lines.append("NOT supported by the retrieved sources:")
        for text in answer.needs_verification:
            lines.append(f"- {text}")

    if answer.unchecked:
        # Deliberately worded as a limit on us, not a finding against the
        # claim. We did not look; that is not the same as looking and
        # finding nothing.
        lines.append("")
        lines.append("Not checked -- no authority for these was found in the "
                     "sources searched, so verify independently:")
        for text in answer.unchecked:
            lines.append(f"- {text}")

    if answer.citations:
        lines.append("")
        lines.append("Sources: " + ", ".join(answer.citations))

    lines.append("")
    lines.append(answer.disclaimer)
    return "\n".join(lines)
