"""Score the treatment classifier against the reporter's own labels.

    .venv/bin/python -m evals.run_treatment
    .venv/bin/python -m evals.run_treatment --limit 40

Ground truth is the Supreme Court Reports' Case Law Reference table -- the
reporter's editorial classification of how a judgment dealt with each
authority. The model never sees it: passages come from body prose before the
headnote's citation block, so this measures reading law, not reading a label.

What this CANNOT measure, and the reason matters: the dataset holds no
OVERRULED case, because our corpus contains no reporter-labelled overruling
where we also hold the overruled judgment. The label whose errors are worst
is therefore unscored here. What is reported instead is how often the model
*reaches* for OVERRULED on passages the reporter labelled otherwise -- every
such reach is a false overruling that the shipped code suppresses.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from legal_ai.agents.treatment import BATCH_SIZE, Treatment, classify_treatments

DATASET = Path(__file__).parent / "datasets" / "treatment.json"

# agents/treatment.py rewrites a model OVERRULED to NOT_CHECKED with this
# reason. Counting it is how a suppressed false overruling stays visible.
_SUPPRESSED = "reserved for the reporter table"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=0, help="cases to run (0 = all)")
    parser.add_argument("--dataset", type=str, default=None)
    args = parser.parse_args()

    cases = json.loads(Path(args.dataset or DATASET).read_text())
    if args.limit:
        cases = cases[: args.limit]
    print(f"{len(cases)} cases\n")

    findings = []
    for start in range(0, len(cases), BATCH_SIZE):
        chunk = cases[start: start + BATCH_SIZE]
        findings.extend(
            classify_treatments([(c["cited"], c["passage"]) for c in chunk])
        )
        print(f"  {len(findings)}/{len(cases)}", flush=True)

    exact = 0
    reached_for_overruled = 0
    not_checked = 0
    confusion: Counter = Counter()
    per_label: dict[str, list[int]] = {}

    for case, finding in zip(cases, findings):
        expected = case["expected"]
        got = finding.treatment.value
        if _SUPPRESSED in (finding.why or ""):
            reached_for_overruled += 1
        if finding.treatment is Treatment.NOT_CHECKED:
            not_checked += 1
        confusion[(expected, got)] += 1
        hits, total = per_label.get(expected, [0, 0])
        per_label[expected] = [hits + (got == expected), total + 1]
        exact += got == expected

    n = max(len(cases), 1)
    print(f"\nexact agreement with the reporter   {exact / n:.2f}  ({exact}/{n})")
    print(f"returned NOT_CHECKED                {not_checked / n:.2f}")
    print(f"reached for OVERRULED (suppressed)  {reached_for_overruled}"
          f"  <- every one is a false overruling avoided")

    print("\nper reporter label:")
    for label, (hits, total) in sorted(per_label.items(), key=lambda kv: -kv[1][1]):
        print(f"  {label:14} {hits}/{total}  {hits / max(total, 1):.2f}")

    print("\nconfusion (reporter -> model), most common first:")
    for (expected, got), count in confusion.most_common(10):
        mark = "  " if expected == got else "X "
        print(f"  {mark}{expected:14} -> {got:14} {count}")


if __name__ == "__main__":
    main()
