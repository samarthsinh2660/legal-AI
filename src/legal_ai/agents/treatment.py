"""Treatment Agent -- how did a later judgment deal with the case it cited?

This is the Shepard's/KeyCite question, and the one a lawyer most assumes a
legal research tool already answers: *is this still good law?* It cannot be
read off the citation graph, because the graph records that A cites B and
nothing about what A made of B. "(2019) 8 SCC 729" is the same string whether
the court followed it, distinguished it, or buried it.

The input is the sentence around each citation
(`ingestion.citations.extract_citation_contexts`), so the model reads the
words that carry the treatment and not the whole judgment.

**Fails to NOT_CHECKED, never to FOLLOWED.** The asymmetry is the point.
Telling a reader a case is good law when it was overruled is worse than
telling them nothing, because it stops them checking; the reverse merely
leaves them where they started. So an unreadable reply, an unrecognised
label, and a citation the model passed over all land in the same place: not
checked. Silence is not approval.

DISTINGUISHED is deliberately not negative. A court distinguishing an earlier
case leaves it good law on its own facts -- treating that as a retirement
would kill live authority, which is the same failure as missing an overruling
pointed the other way.

One batched call for many citations.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum

from legal_ai.config import DEFAULT_CONFIG
from legal_ai.llm.client import generate

# Citations per call. Each carries ~1,000 characters of context, so this is
# the window and not a preference.
BATCH_SIZE = 12


class Treatment(str, Enum):
    FOLLOWED = "FOLLOWED"
    DISTINGUISHED = "DISTINGUISHED"
    OVERRULED = "OVERRULED"

    # Cited without being adopted or doubted -- the ordinary case.
    CONSIDERED = "CONSIDERED"

    # Not a treatment. The classification did not run or could not be read.
    NOT_CHECKED = "NOT_CHECKED"

    @property
    def is_negative(self) -> bool:
        """Whether this treatment undermines the cited case as authority.

        Only overruling does. Distinguishing confines a case to its facts
        and leaves it standing, and a reader told otherwise would abandon
        an authority that still binds.
        """
        return self is Treatment.OVERRULED


@dataclass(frozen=True)
class TreatmentFinding:
    citation: str
    treatment: Treatment
    why: str = ""


_PROMPT = """You read how an Indian court dealt with a case it cited.

For each numbered passage, say how the citing court treated the cited case:

FOLLOWED       - applied it as binding or persuasive authority, agreed with it
DISTINGUISHED  - declined to apply it because the facts or issue differ. The
                 cited case remains good law; the court simply says it does
                 not govern here.
OVERRULED      - held it wrongly decided, or no longer good law. Use this ONLY
                 for the cited case being displaced as authority -- not for
                 allowing an appeal, reversing the judgment under appeal, or
                 setting aside the order below. Those are outcomes of THIS
                 case, not treatments of the CITED one.
CONSIDERED     - referred to, summarised, or noted without adopting or doubting
                 it. This is the ordinary case; prefer it when unsure.

If the passage does not make the treatment clear, answer CONSIDERED. Never
guess OVERRULED: reporting an overruling that did not happen retires an
authority that still binds.

PASSAGES:
{body}

Reply with JSON only:
{{"treatments": [{{"n": 1, "treatment": "...", "why": "a few words"}}]}}"""


def _render(cited: list[tuple[str, str]]) -> str:
    return "\n\n".join(
        f"{index}. CITED CASE: {citation}\n   PASSAGE: {context}"
        for index, (citation, context) in enumerate(cited, start=1)
    )


def classify_treatments(
    cited: list[tuple[str, str]],
    chain: tuple[str, ...] = DEFAULT_CONFIG.case_model_chain,
) -> list[TreatmentFinding]:
    """A finding for each (citation, context) in `cited`, in the same order.

    Anything the model does not rule on comes back NOT_CHECKED. Runs on
    `case_model_chain` -- this is close reading of two passages for
    disagreement, the task Gemma measured recall 1.00 on against
    gemini-flash's 0.20 (evals/run_contradictions.py, 2026-08-24).
    """
    if not cited:
        return []

    raw = generate(
        _PROMPT.format(body=_render(cited)),
        chain=chain,
        max_output_tokens=DEFAULT_CONFIG.extraction_model_max_tokens,
    )

    by_index: dict[int, tuple[Treatment, str]] = {}
    try:
        payload = json.loads(raw[raw.index("{"): raw.rindex("}") + 1])
        for item in payload.get("treatments", []):
            try:
                treatment = Treatment(str(item.get("treatment", "")).strip().upper())
            except ValueError:
                # An unrecognised label is not a licence to approve.
                continue
            if treatment is Treatment.NOT_CHECKED:
                # Not the model's to give: it was asked to classify.
                continue
            if treatment is Treatment.OVERRULED:
                # Measured 2026-08-30: the model returned OVERRULED twice on
                # the real corpus and was wrong both times -- once on a
                # phantom edge from a page-header citation collision, once
                # where the cited case was marked "affirmed" in a reference
                # list and a different case on the same line was overruled.
                #
                # 0 for 2 on the label whose errors are worst. Reserved for
                # the reporter's own table, which states it outright rather
                # than inferring it from prose. NOT_CHECKED here withholds
                # the clean bill without asserting a retirement.
                by_index[int(item["n"])] = (
                    Treatment.NOT_CHECKED,
                    "model reported overruling; reserved for the reporter table",
                )
                continue
            by_index[int(item["n"])] = (treatment, str(item.get("why", ""))[:120])
    except (ValueError, KeyError, TypeError):
        return [
            TreatmentFinding(citation, Treatment.NOT_CHECKED, "reply was unreadable")
            for citation, _context in cited
        ]

    findings = []
    for index, (citation, _context) in enumerate(cited, start=1):
        treatment, why = by_index.get(
            index, (Treatment.NOT_CHECKED, "no treatment returned for this citation")
        )
        findings.append(TreatmentFinding(citation, treatment, why))
    return findings
