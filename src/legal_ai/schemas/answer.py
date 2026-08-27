"""DraftAnswer -- the contract between the system and the research screen.

Slots, not prose. `PROJECT_STRUCTURE.md` §3: the UI does not free-render a
paragraph, it renders these fields. That is what lets the screen show a
claim we could not verify differently from one we could -- in free prose
the two look identical, same font, same confidence, and the reader has no
way to tell them apart.

Assembled deterministically from claims and Evidence. No model call: the
inputs are already structured, and asking a model to re-render structured
data only gives it an opportunity to drop a citation.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from legal_ai.schemas.verification import Claim

DISCLAIMER = (
    "This is legal information generated from primary sources, not legal "
    "advice, and no lawyer-client relationship arises from it. Verify every "
    "provision and authority before relying on it."
)


@dataclass(frozen=True)
class DraftAnswer:
    """What the research screen renders."""

    question: str

    # One or two sentences answering the question directly.
    lede: str = ""

    # Claims that survived verification, each carrying its own ids.
    key_elements: tuple[Claim, ...] = ()

    # Document ids, not prose -- a provision a reader cannot open is not
    # usable, and the id keeps it checkable.
    applicable_law: tuple[str, ...] = ()
    key_judgments: tuple[str, ...] = ()

    # Claims the retrieved evidence does not support -- a finding against
    # the claim. Kept and labelled rather than dropped: silently removing
    # them would leave the reader unable to tell a short answer from an
    # incomplete one.
    needs_verification: tuple[str, ...] = ()

    # Claims we could NOT check, which is a different thing and must not
    # read the same. Either we do not hold the material, or semantic
    # verification was not enabled for this run. Telling a lawyer a claim
    # is unsupported when we simply did not look is a claim we cannot make.
    unchecked: tuple[str, ...] = ()

    # Claims the evidence supports in part -- true but overstated, or
    # narrowed by a condition the claim drops.
    partially_supported: tuple[str, ...] = ()

    citations: tuple[str, ...] = ()
    disclaimer: str = DISCLAIMER

    @property
    def is_complete(self) -> bool:
        """Whether every claim made was verified and supported.

        `unchecked` counts: an answer whose claims were never checked is
        not a complete answer, however true it may turn out to be.
        """
        return not (self.needs_verification or self.unchecked
                    or self.partially_supported)


@dataclass(frozen=True)
class AnalysisResult:
    """What the Analyst produced, before verification runs over it."""

    claims: tuple[Claim, ...] = ()
    lede: str = ""

    # Identifiers the model cited that were never in front of it, dropped
    # before they reached a claim. Kept as a count of what validation
    # caught: it is the difference between a fabricated citation a reader
    # would trust and a visibly unsupported statement, and it is the number
    # worth watching when the model changes.
    dropped_ids: tuple[str, ...] = field(default_factory=tuple)
