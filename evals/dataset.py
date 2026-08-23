"""Evaluation questions and the document ids that correctly answer them.

Ground truth is verified by reading the section title, never by matching
patterns against it: a title search for "cheating" returns *Cheating at
games and gambling in street*. A mislabelled answer makes the harness report
a failure that retrieval cannot fix, which is worse than no measurement --
the number still gets believed.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

DEFAULT_DATASET = Path(__file__).parent / "datasets" / "retrieval.json"

# Questions whose correct answer is a SET of provisions across Acts. Scored
# by coverage, not rank -- see evals.evaluators.coverage.
MULTI_ANGLE_DATASET = Path(__file__).parent / "datasets" / "multi_angle.json"


@dataclass(frozen=True)
class EvalQuestion:
    id: str
    question: str
    # Several ids because near-duplicate provisions exist across Acts;
    # retrieving any one of them is a correct answer.
    expected: tuple[str, ...]
    note: str = ""
    # Named angles, for multi-angle questions. Empty for lookup questions.
    angles: tuple[str, ...] = ()


def load_questions(path: Path | None = None) -> list[EvalQuestion]:
    raw = json.loads((path or DEFAULT_DATASET).read_text())
    return [
        EvalQuestion(
            id=item["id"],
            question=item["question"],
            expected=tuple(item["expected"]),
            note=item.get("note", ""),
            angles=tuple(item.get("angles", ())),
        )
        for item in raw
    ]
