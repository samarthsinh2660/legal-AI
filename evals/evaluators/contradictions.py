"""Score contradiction detection against planted ground truth.

Graded on **document ids, not prose**. Asking whether the model's sentence
means the same as the label's sentence is itself a judgement call, and
grading a model's output with another model produces a number nobody can
check. A planted conflict is between two named documents; a detection
counts when the reported text names both of them. That is objective.

Negative controls carry the weight here. A detector that answers
"contradiction" to everything scores perfect recall, so recall alone says
nothing -- the false-positive rate on cases whose documents genuinely agree
is what separates a useful detector from an eager one.
"""

from __future__ import annotations

from dataclasses import dataclass


def _names_both(text: str, pair: tuple[str, str]) -> bool:
    return all(document_id in text for document_id in pair)


def detected_pairs(
    reported: tuple[str, ...],
    planted: list[tuple[str, str]],
) -> set[tuple[str, str]]:
    """Planted pairs that some reported contradiction names both sides of."""
    return {
        tuple(pair)
        for pair in planted
        if any(_names_both(text, tuple(pair)) for text in reported)
    }


def spurious(reported: tuple[str, ...], planted: list[tuple[str, str]]) -> list[str]:
    """Reported contradictions that match no planted pair.

    On a negative control every report is spurious. On a case with planted
    conflicts this is only meaningful because the datasets label every
    conflict present -- a partially labelled case would count a real find
    as a false alarm.
    """
    return [
        text
        for text in reported
        if not any(_names_both(text, tuple(pair)) for pair in planted)
    ]


@dataclass(frozen=True)
class ContradictionScore:
    planted: int
    found: int
    false_alarms: int
    controls: int
    controls_clean: int

    @property
    def recall(self) -> float:
        """Share of planted conflicts detected. 1.0 when none were planted,
        since nothing was missed."""
        return self.found / self.planted if self.planted else 1.0

    @property
    def control_precision(self) -> float:
        """Share of negative-control cases left alone. This is the number
        that stops "always say yes" from looking good."""
        return self.controls_clean / self.controls if self.controls else 1.0


def score(results: list[tuple[tuple[str, ...], list[tuple[str, str]]]]) -> ContradictionScore:
    """Aggregate (reported, planted) over a run."""
    planted = found = false_alarms = controls = controls_clean = 0
    for reported, expected in results:
        planted += len(expected)
        found += len(detected_pairs(reported, expected))
        alarms = len(spurious(reported, expected))
        false_alarms += alarms
        if not expected:
            controls += 1
            controls_clean += 1 if not reported else 0
    return ContradictionScore(
        planted=planted,
        found=found,
        false_alarms=false_alarms,
        controls=controls,
        controls_clean=controls_clean,
    )
