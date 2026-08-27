"""Claim -- a statement the system intends to make, and what it rests on --
and the verdicts a checker can reach about one.

Here rather than in `verification/` because both sides need it: the Analyst
produces claims and the verifier consumes them, and `agents/` may import
`schemas/` but not `verification/`. Keeping the type in the checker would
make every producer depend on its own checker.

Structured, never prose. A summary that ends "Sources: a, b, c" cannot be
verified -- nothing says which sentence rests on which source. One claim
carrying its own ids can be checked by lookup.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


@dataclass(frozen=True)
class Claim:
    """A statement the system intends to make, and what it rests on.

    An empty `evidence_ids` is representable on purpose. A claim with
    nothing behind it is exactly what the verifier exists to catch, and
    refusing to construct one would hide the failure instead of reporting
    it.
    """

    text: str
    evidence_ids: tuple[str, ...] = ()
    paragraph: int | None = None


class Verdict(str, Enum):
    """What a checker concluded about one claim.

    Four, not two, because the two-state version cannot tell a lawyer the
    difference between "the law is against you" and "we do not have the
    book". Our corpus is a few thousand judgments against an Indian corpus
    in the crores, so the second is our normal condition, and reporting it
    as the first would be a claim we cannot support.
    """

    SUPPORTED = "SUPPORTED"
    PARTIALLY_SUPPORTED = "PARTIALLY_SUPPORTED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    UNSUPPORTED = "UNSUPPORTED"

    @property
    def is_a_finding_against_the_claim(self) -> bool:
        """True where we looked at relevant material and it did not support
        the claim. False for INSUFFICIENT_EVIDENCE, which is a statement
        about our shelf, not about the law."""
        return self in (Verdict.UNSUPPORTED, Verdict.PARTIALLY_SUPPORTED)


@dataclass(frozen=True)
class ClaimVerdict:
    """One claim's outcome, and which stage reached it.

    `stage` is not decoration. If the deterministic stages never catch
    anything, they are not earning the code that runs them; if the model
    stage is reached for every claim, the funnel is not funnelling. Both
    are measurable only if each verdict remembers where it came from.
    """

    claim: Claim
    verdict: Verdict
    reason: str
    stage: str

    @property
    def needs_flagging(self) -> bool:
        return self.verdict is not Verdict.SUPPORTED


@dataclass(frozen=True)
class VerificationReport:
    verdicts: list[ClaimVerdict] = field(default_factory=list)
    model_calls: int = 0

    @property
    def all_supported(self) -> bool:
        return all(v.verdict is Verdict.SUPPORTED for v in self.verdicts)

    def of(self, verdict: Verdict) -> list[ClaimVerdict]:
        return [v for v in self.verdicts if v.verdict is verdict]

    @property
    def flagged(self) -> list[ClaimVerdict]:
        """Everything the reader must see a mark against. Deliberately
        includes INSUFFICIENT_EVIDENCE: an unverifiable claim presented
        unmarked is the failure this whole phase exists to prevent."""
        return [v for v in self.verdicts if v.needs_flagging]

    @property
    def unsupported_texts(self) -> list[str]:
        """Claims we have a finding against -- not claims we merely could
        not check. Used where the graph decides whether re-research could
        help, and re-researching a claim whose evidence contradicts it
        cannot help."""
        return [v.claim.text for v in self.verdicts
                if v.verdict is Verdict.UNSUPPORTED]
