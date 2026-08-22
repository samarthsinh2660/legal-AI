"""Measure multi-angle research: does decomposition find MORE of the answer?

    .venv/bin/python -m evals.run_multi_angle
    .venv/bin/python -m evals.run_multi_angle --single

Scored by COVERAGE, not rank. "My builder is three years late" is answered
by the refund provision AND the allottee's rights AND which forum hears it;
finding one of four is not a quarter of an answer, and a rank metric cannot
say so.

`--single` forces one angle, which is the control: it isolates what
decomposition contributes from what the research loop contributes.

Defaults are deliberately cheap. Measured 2026-08-22: 3 angles x 2 rounds x
8 steps took 21 minutes for ONE question -- 3.5 hours for the set, which is
too slow to learn from. One round of four steps keeps a run iterable, and
the control must be run at the same settings for the comparison to mean
anything.
"""

from __future__ import annotations

import argparse

from evals.preflight import FailureTracker, require_model
from evals.dataset import MULTI_ANGLE_DATASET, load_questions
from evals.evaluators.coverage import complete_rate, coverage_at_k, mean_coverage
from legal_ai.agents.supervisor import supervise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--single", action="store_true", help="force one angle (control)")
    parser.add_argument("--max-angles", type=int, default=3)
    parser.add_argument("--k", type=int, default=10)
    parser.add_argument("--limit", type=int, default=0, help="first N questions only")
    parser.add_argument("--max-rounds", type=int, default=1,
                        help="rounds per angle (1 keeps a run iterable)")
    parser.add_argument("--max-steps", type=int, default=4,
                        help="tool steps per plan")
    parser.add_argument("--parallel", action="store_true",
                        help="run angles concurrently (rate-limited on the free tier)")
    args = parser.parse_args()

    require_model()
    tracker = FailureTracker()

    max_angles = 1 if args.single else args.max_angles
    questions = load_questions(MULTI_ANGLE_DATASET)
    if args.limit:
        questions = questions[: args.limit]

    coverages: list[float] = []
    spawned: list[int] = []
    for question in questions:
        result = supervise(
            question.question,
            max_angles=max_angles,
            max_rounds=args.max_rounds,
            max_steps=args.max_steps,
            parallel=args.parallel,
        )
        ids = [item.document_id for item in result.evidence if item.document_id]
        found = coverage_at_k(ids, question.expected, args.k)
        tracker.record_model_failures()
        coverages.append(found)
        spawned.append(result.agents_spawned)
        missing = set(question.expected) - set(ids[: args.k])
        print(
            f"  {question.id:<28} {found:.0%} of {len(question.expected)}  "
            f"agents {result.agents_spawned}  missing {sorted(missing) if missing else '-'}",
            flush=True,
        )

    label = "single angle" if args.single else f"up to {max_angles} angles"
    print(
        f"\n{label:<16} coverage@{args.k} {mean_coverage(coverages):.0%}  "
        f"complete {complete_rate(coverages):.0%}  "
        f"agents/question {sum(spawned)/len(spawned):.1f}"
    )


if __name__ == "__main__":
    main()
