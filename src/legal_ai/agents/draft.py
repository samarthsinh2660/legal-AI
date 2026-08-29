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

from legal_ai.retrieval.authority import Authority, rank_by_authority
from legal_ai.schemas.answer import AnalysisResult, DraftAnswer
from legal_ai.schemas.evidence import Evidence
from legal_ai.schemas.verification import Claim, Verdict

_STATUTE_TYPES = frozenset({"act", "section"})


def _ordered_judgments(
    judgment_ids: list[str], authority: dict[str, Authority] | None
) -> tuple[str, ...]:
    """Judgments strongest first, or by id when nothing is known.

    Ordering by document_id -- the previous behaviour, and still the
    fallback -- is alphabetical order over opaque identifiers, which puts a
    single-judge order above the Constitution Bench that settled the point.

    A judgment absent from `authority` is ranked as uncited rather than
    dropped: the lookup runs over the graph, which need not hold every
    retrieved judgment, and a gap there must not remove a citation from the
    answer.
    """
    if not authority:
        return tuple(sorted(judgment_ids))
    ranked = rank_by_authority(
        [authority.get(i, Authority(document_id=i)) for i in sorted(judgment_ids)]
    )
    return tuple(item.document_id for item in ranked)


def build_answer(
    question: str,
    analysis: AnalysisResult,
    evidence: list[Evidence],
    unsupported: tuple[str, ...] = (),
    report=None,
    authority: dict[str, "Authority"] | None = None,
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
    by_stage: dict[str, str] = {}
    if report is not None:
        by_text = {v.claim.text: v.verdict for v in report.verdicts}
        by_stage = {v.claim.text: v.stage for v in report.verdicts}
    skipped_support = False

    unsupported_set = set(unsupported)
    supported: list[Claim] = []
    flagged: list[str] = []
    unchecked: list[str] = []
    partial: list[str] = []

    for claim in analysis.claims:
        verdict = by_text.get(claim.text)

        # The verdict wins wherever there is one. `unsupported` is the
        # graph's re-research set, which is NOT the same as a finding
        # against the claim: it also carries claims citing a real document
        # this thread never retrieved, precisely because another pass can
        # fetch it. Reading that list as findings would tell a lawyer we
        # checked and found against them when we simply did not look.
        if verdict is not None:
            if verdict is Verdict.UNSUPPORTED:
                flagged.append(claim.text)
            elif verdict is Verdict.PARTIALLY_SUPPORTED:
                partial.append(claim.text)
            elif verdict is Verdict.INSUFFICIENT_EVIDENCE:
                if by_stage.get(claim.text) == "skipped":
                    supported.append(claim)
                    skipped_support = True
                else:
                    unchecked.append(claim.text)
            else:
                supported.append(claim)
            continue

        # No report: fall back to the text list, which for such callers has
        # always meant a finding against the claim. A claim citing nothing
        # has nothing for a verifier to have checked either way.
        if not claim.evidence_ids or claim.text in unsupported_set:
            flagged.append(claim.text)
        elif verdict is Verdict.UNSUPPORTED:
            flagged.append(claim.text)
        elif verdict is Verdict.PARTIALLY_SUPPORTED:
            partial.append(claim.text)
        elif verdict is Verdict.INSUFFICIENT_EVIDENCE:
            if by_stage.get(claim.text) == "skipped":
                # Quick mode: the citation was verified, only support was
                # not. Reported once at the answer level rather than as a
                # warning against every claim.
                supported.append(claim)
                skipped_support = True
            else:
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
        key_judgments=_ordered_judgments(judgments, authority),
        needs_verification=tuple(flagged),
        unchecked=tuple(unchecked),
        partially_supported=tuple(partial),
        support_not_checked=skipped_support,
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

    if answer.support_not_checked:
        lines.append("")
        lines.append("Citations above were verified against the corpus, but the "
                     "statements were not individually checked against the source "
                     "text. Re-run with verification enabled for that.")

    if answer.citations:
        lines.append("")
        lines.append("Sources: " + ", ".join(answer.citations))

    lines.append("")
    lines.append(answer.disclaimer)
    return "\n".join(lines)
