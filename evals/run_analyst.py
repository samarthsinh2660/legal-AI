"""Measure the Analyst: does it cite what it was shown, or invent?

    .venv/bin/python -m evals.run_analyst --limit 10

Three numbers, all objective -- no judging prose, no model grading a model.

    grounded         share of claims carrying at least one identifier that
                     was actually retrieved. A claim without one is a
                     statement with nothing behind it.

    fabricated       identifiers the model cited that were never in front
                     of it. Validation drops these before they reach a
                     claim, so this counts what would otherwise have been a
                     false citation in a legal answer -- the single worst
                     failure this system can produce.

    verified         share surviving the groundedness check, which resolves
                     each identifier against the corpus rather than merely
                     against the retrieved set.

Run it before and after changing the model or the prompt. A model that
writes better prose but fabricates more identifiers is worse, and prose
quality is exactly what a benchmark cannot see.
"""

from __future__ import annotations

import argparse

from evals.dataset import load_questions
from evals.preflight import FailureTracker, require_model
from legal_ai.agents.analyst import analyse
from legal_ai.agents.supervisor import research
from legal_ai.knowledge.static.db import get_connection
from legal_ai.llm.client import MODEL_USAGE, reset_model_usage
from legal_ai.verification.groundedness import check_groundedness


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=10, help="first N questions")
    parser.add_argument("--model", type=str, default=None, help="pin one model")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    require_model()
    reset_model_usage()
    tracker = FailureTracker()

    questions = load_questions()[: args.limit]
    chain = (args.model,) if args.model else None

    total_claims = grounded = verified = 0
    fabricated: list[str] = []
    no_claims = 0

    conn = get_connection()
    try:
        for question in questions:
            found = research(question.question, conn=conn, chain=chain)
            result = analyse(question.question, found.evidence)
            tracker.record_model_failures()

            if not result.claims:
                no_claims += 1

            total_claims += len(result.claims)
            grounded += sum(1 for c in result.claims if c.evidence_ids)
            fabricated.extend(result.dropped_ids)

            if result.claims:
                retrieved = {e.document_id for e in found.evidence if e.document_id}
                check = check_groundedness(
                    list(result.claims), conn, available_ids=retrieved
                )
                verified += len(check.grounded)

            print(
                f"  {question.id:32} claims {len(result.claims):2}  "
                f"grounded {sum(1 for c in result.claims if c.evidence_ids):2}  "
                f"fabricated {len(result.dropped_ids)}"
            )
            if args.verbose:
                for claim in result.claims:
                    print(f"      - {claim.text[:80]} {list(claim.evidence_ids)}")
    finally:
        conn.close()

    print()
    print(f"questions            {len(questions)}  ({no_claims} produced no claims)")
    print(f"claims               {total_claims}")
    if total_claims:
        print(f"grounded             {grounded}/{total_claims}  {grounded/total_claims:.0%}")
        print(f"verified             {verified}/{total_claims}  {verified/total_claims:.0%}")
    print(f"fabricated ids       {len(fabricated)}   {sorted(set(fabricated))[:5]}")
    print(f"models used          {dict(MODEL_USAGE)}")
    print()
    print("A fabricated identifier is one validation caught. Without that check")
    print("it would have reached the reader as a citation they could not tell")
    print("apart from a real one.")


if __name__ == "__main__":
    main()
