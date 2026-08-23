"""Refuse to run an eval that cannot reach a model.

An eval whose model calls are failing does not produce a low score, it
produces a meaningless one -- the agent looks bad when in fact it never ran.
That is worse than no measurement, because the number still gets written
down and believed.

Learned on 2026-08-21: a multi-angle run reported 5% coverage against a 22%
control. The difference was not the design under test; the whole model chain
had hit its daily cap partway through, and questions on the identical code
path scored 67% and 0% in successive runs.
"""

from __future__ import annotations

from legal_ai.llm.client import MODEL_CHAIN, AllModelsUnavailable, generate


class EvalPreconditionFailed(RuntimeError):
    """Raised before an eval starts, so no misleading number is produced."""


def require_model() -> str:
    """Confirm at least one model in the chain answers. Returns its reply."""
    try:
        return generate("Reply with the single word: ok")
    except AllModelsUnavailable as error:
        raise EvalPreconditionFailed(
            f"No model in the chain of {len(MODEL_CHAIN)} is reachable, so this "
            f"eval would measure API availability rather than the system. "
            f"Re-run when quota resets.\n{error}"
        ) from error


class FailureTracker:
    """Abort a run once model failures make the result untrustworthy.

    A few transient failures degrade a run acceptably. A run where most
    questions could not reach a model is not a low score, it is no score.
    """

    def __init__(self, tolerance: float = 0.2) -> None:
        self.tolerance = tolerance
        self.attempts = 0
        self.failures = 0
        self._seen_failures = 0

    def record_model_failures(self) -> None:
        """Record one question, failed only if the model chain was actually
        unreachable during it.

        Distinct from the question finding nothing: an agent that searched
        and came up empty is a research result, and counting it as an API
        failure would abort a run that is working correctly.
        """
        from legal_ai.llm import client

        before = self._seen_failures
        self._seen_failures = client.UNAVAILABLE_COUNT
        self.record(failed=client.UNAVAILABLE_COUNT > before)

    def record(self, failed: bool) -> None:
        self.attempts += 1
        self.failures += 1 if failed else 0
        if self.attempts >= 5 and self.failures / self.attempts > self.tolerance:
            raise EvalPreconditionFailed(
                f"{self.failures} of {self.attempts} questions could not reach a "
                f"model. Aborting rather than reporting a score that measures "
                f"API availability. Re-run when quota resets."
            )
