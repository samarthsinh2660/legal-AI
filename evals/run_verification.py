"""Measure the verifier: does it catch a claim its cited text does not support?

    .venv/bin/python -m evals.run_verification
    .venv/bin/python -m evals.run_verification --model gemma-4-31b-it --runs 3

Answers are **not generated here.** The 50 claims are frozen fixtures written
against the real stored text of the sections they cite, so the only variable
in a run is the verifier. That makes the inputs deterministic, the run cheap
to repeat across the model chain, and the number attributable to the checker
rather than to whichever model happened to write the answer.

Four numbers, and the last two are the ones that decide whether semantic
verification can be turned on by default:

  catch rate     of the claims that should be flagged, how many were
  false alarms   of the claims that are fine, how many were flagged anyway
  residue rate   how many claims reached the model at all -- the funnel's
                 whole cost argument is that this is small
  flip rate      how often the same claim changes verdict across identical
                 runs. LLM judges are self-inconsistent instruments; a
                 verifier that disagrees with itself cannot be trusted to
                 disagree with an answer.
"""

from __future__ import annotations

import argparse
import collections
import json
from pathlib import Path

from legal_ai.config import DEFAULT_CONFIG
from legal_ai.knowledge.static.db import get_connection
from legal_ai.schemas.verification import Claim, Verdict
from legal_ai.verification.pipeline import verify

DATASET = Path(__file__).parent / "datasets" / "verification.json"

# A verdict of SUPPORTED means "say this plainly". Everything else means
# "put a mark next to it", so for catch rate the question is only whether
# the reader is warned, not whether the exact shade of warning matched.
def _should_flag(verdict: str) -> bool:
    return verdict != Verdict.SUPPORTED.value


def run_once(cases, conn, use_model, chain, checkpoint=None):
    """`checkpoint` is written after every case.

    A run over the chain takes tens of minutes of model calls, and writing
    the report only at the end means an interrupted run produces nothing at
    all -- which is what happened on 2026-08-27. Partial results are still
    a measurement; discarding them is a choice, and the wrong one.
    """
    results = []
    for case in cases:
        claim = Claim(case["claim"], tuple(case["evidence_ids"]))
        available = {i for i in case["evidence_ids"]}
        report = verify([claim], conn, available_ids=available,
                        use_model=use_model, chain=chain)
        verdict = report.verdicts[0]
        results.append({
            "id": case["id"],
            "expected": case["expected_verdict"],
            "got": verdict.verdict.value,
            "stage": verdict.stage,
            "expected_stage": case.get("expected_stage"),
            "reason": verdict.reason,
            "model_calls": report.model_calls,
        })
        if checkpoint is not None:
            checkpoint.write_text(json.dumps(results, indent=2))
        print(f"  {case['id']:10} want {case['expected_verdict']:22} "
              f"got {verdict.verdict.value:22} [{verdict.stage}]", flush=True)
    return results


def score(results):
    exact = sum(1 for r in results if r["got"] == r["expected"])
    should_flag = [r for r in results if _should_flag(r["expected"])]
    should_not = [r for r in results if not _should_flag(r["expected"])]
    caught = [r for r in should_flag if _should_flag(r["got"])]
    alarms = [r for r in should_not if _should_flag(r["got"])]
    reached_model = [r for r in results if r["stage"] == "semantic"]
    stage_wrong = [r for r in results
                   if r["expected_stage"] and r["stage"] != r["expected_stage"]]
    return {
        "exact_verdict": exact / len(results),
        "catch_rate": len(caught) / len(should_flag) if should_flag else 1.0,
        "false_alarms": len(alarms) / len(should_not) if should_not else 0.0,
        "residue_rate": len(reached_model) / len(results),
        "model_calls": sum(r["model_calls"] for r in results),
        "stage_mismatches": len(stage_wrong),
        "_alarms": [r["id"] for r in alarms],
        "_missed": [r["id"] for r in should_flag if not _should_flag(r["got"])],
        "_stage_wrong": [(r["id"], r["expected_stage"], r["stage"]) for r in stage_wrong],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", help="single model instead of the chain")
    parser.add_argument("--runs", type=int, default=1, help="repeat to measure flip rate")
    parser.add_argument("--no-model", action="store_true",
                        help="deterministic stages only")
    parser.add_argument("--report", default="verification_eval.json")
    args = parser.parse_args()

    cases = json.loads(DATASET.read_text())["cases"]
    chain = (args.model,) if args.model else DEFAULT_CONFIG.model_chain
    conn = get_connection()

    runs = []
    for n in range(args.runs):
        results = run_once(cases, conn, use_model=not args.no_model, chain=chain,
                           checkpoint=Path(f"{args.report}.run{n + 1}.partial"))
        runs.append(results)
        s = score(results)
        print(f"run {n + 1}: exact {s['exact_verdict']:.2f}  "
              f"catch {s['catch_rate']:.2f}  false alarms {s['false_alarms']:.2f}  "
              f"residue {s['residue_rate']:.2f}  calls {s['model_calls']}")

    final = score(runs[-1])

    # Flip rate: same claim, same input, different verdict across runs.
    flips = 0
    if len(runs) > 1:
        by_id = collections.defaultdict(set)
        for results in runs:
            for r in results:
                by_id[r["id"]].add(r["got"])
        flips = sum(1 for verdicts in by_id.values() if len(verdicts) > 1)
        final["flip_rate"] = flips / len(cases)

    print()
    print(f"cases              {len(cases)}")
    print(f"exact verdict      {final['exact_verdict']:.2f}")
    print(f"catch rate         {final['catch_rate']:.2f}   (of claims that should be flagged)")
    print(f"false alarms       {final['false_alarms']:.2f}   (of claims that are fine)")
    print(f"residue rate       {final['residue_rate']:.2f}   (reached the model)")
    print(f"model calls        {final['model_calls']}")
    print(f"stage mismatches   {final['stage_mismatches']}")
    if len(runs) > 1:
        print(f"flip rate          {final['flip_rate']:.2f}   (over {len(runs)} runs)")
    if final["_missed"]:
        print(f"  missed:      {final['_missed']}")
    if final["_alarms"]:
        print(f"  false alarms:{final['_alarms']}")
    if final["_stage_wrong"]:
        print(f"  wrong stage: {final['_stage_wrong']}")

    Path(args.report).write_text(json.dumps(
        {"model": args.model or "chain", "runs": runs, "score": final}, indent=2))
    print(f"\nreport: {args.report}")
    conn.close()


if __name__ == "__main__":
    main()
