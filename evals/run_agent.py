"""Measure the research agent against the same benchmark as plain retrieval.

    .venv/bin/python -m evals.run_agent

**This benchmark is noisy.** The query is written by a model, so the same
configuration scores differently run to run -- measured at +/-0.15 MRR on
identical code. A single run cannot separate two configurations that differ
by less than that, and comparing single runs is how a whole day gets spent
tuning against noise. Run each configuration several times and compare the
spread, not the number.

Ranking is the order the agent returns its evidence in, so this measures the
same thing `evals.run` does and the numbers are comparable.
"""

from __future__ import annotations

import argparse

from evals.preflight import FailureTracker, require_model
from legal_ai.llm.client import MODEL_USAGE, reset_model_usage
from evals.dataset import load_questions
from evals.evaluators.ranking import first_relevant_rank, mean_reciprocal_rank, recall_at_k
from legal_ai.agents.supervisor import research
from legal_ai.knowledge.static.db import get_connection



def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=0, help="first N questions only")
    args = parser.parse_args()

    require_model()
    reset_model_usage()
    tracker = FailureTracker()

    questions = load_questions()
    if args.limit:
        questions = questions[: args.limit]

    conn = get_connection()
    ranks: list[int | None] = []
    try:
        for question in questions:
            result = research(question.question, conn=conn)
            ids = [item.document_id for item in result.evidence if item.document_id]
            rank = first_relevant_rank(ids, question.expected)
            tracker.record_model_failures()
            ranks.append(rank)
            print(
                f"  {question.id:<30} {'miss' if rank is None else f'rank {rank}':<8} "
                f"angles {result.agents_spawned}  kept {len(result.evidence)}  "
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
    print(f"\nmodels used: {dict(sorted(MODEL_USAGE.items(), key=lambda kv: -kv[1]))}")
    if len(MODEL_USAGE) > 1:
        print("MIXED MODELS -- the chain fell through partway, so later questions")
        print("were answered by a different model than earlier ones. Not one measurement.")
    print("\nOne run only. Repeat before comparing this to another configuration:")
    print("the query is model-written, so run-to-run spread is roughly +/-0.15 MRR.")


if __name__ == "__main__":
    main()
