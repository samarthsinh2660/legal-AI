"""Measure the research agent against the same benchmark as plain retrieval.

    .venv/bin/python -m evals.run_agent

The bar is MRR 0.670 -- what a single LLM query-rewrite call achieves
(evals.run --rewrite). A full plan-execute-validate loop that cannot beat
one rewrite call is not worth its cost, and the honest response would be to
ship the rewrite alone.

Ranking is the order the agent returns its evidence in, so this measures the
same thing `evals.run` does and the numbers are comparable.
"""

from __future__ import annotations

import argparse

from evals.preflight import FailureTracker, require_model
from evals.dataset import load_questions
from evals.evaluators.ranking import first_relevant_rank, mean_reciprocal_rank, recall_at_k
from legal_ai.agents.research import research_angle
from legal_ai.knowledge.static.db import get_connection

BAR_MRR = 0.670


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-rounds", type=int, default=2)
    parser.add_argument("--max-steps", type=int, default=8)
    parser.add_argument("--limit", type=int, default=0, help="first N questions only")
    args = parser.parse_args()

    require_model()
    tracker = FailureTracker()

    questions = load_questions()
    if args.limit:
        questions = questions[: args.limit]

    conn = get_connection()
    ranks: list[int | None] = []
    try:
        for question in questions:
            result = research_angle(
                question.question,
                max_rounds=args.max_rounds,
                max_steps=args.max_steps,
                conn=conn,
            )
            ids = [item.document_id for item in result.evidence if item.document_id]
            rank = first_relevant_rank(ids, question.expected)
            tracker.record_model_failures()
        ranks.append(rank)
            print(
                f"  {question.id:<30} {'miss' if rank is None else f'rank {rank}':<8} "
                f"rounds {result.rounds}  kept {len(result.evidence)}  "
                f"dropped {len(result.dropped)}",
                flush=True,
            )
    finally:
        conn.close()

    mrr = mean_reciprocal_rank(ranks)
    print(
        f"\nagent      MRR {mrr:.3f}  r@1 {recall_at_k(ranks,1):.0%}  "
        f"r@5 {recall_at_k(ranks,5):.0%}  r@10 {recall_at_k(ranks,10):.0%}"
    )
    print(f"bar        MRR {BAR_MRR:.3f}  (single rewrite call)")
    print("VERDICT    " + ("agent clears the bar" if mrr > BAR_MRR else "agent does NOT clear the bar"))


if __name__ == "__main__":
    main()
