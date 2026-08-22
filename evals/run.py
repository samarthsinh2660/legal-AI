"""Run the evaluation dataset through Phase 2 retrieval and report metrics.

    .venv/bin/python -m evals.run
    .venv/bin/python -m evals.run --no-rerank
    .venv/bin/python -m evals.run --limit 20
    .venv/bin/python -m evals.run --rewrite

Reports retrieval quality only. It measures whether the correct provision
comes back and where it ranks -- not whether an answer built on it is
correct, which is what the groundedness evaluators will measure once agents
exist.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from evals.dataset import EvalQuestion, load_questions
from evals.evaluators.ranking import first_relevant_rank, mean_reciprocal_rank, recall_at_k
from legal_ai.retrieval.hybrid import hybrid_search


def run_question(
    question: EvalQuestion, limit: int, rerank: bool, rewrite: bool = False
) -> int | None:
    text = question.question
    if rewrite:
        from evals.rewrite import rewrite_query

        text = rewrite_query(text)
    evidence = hybrid_search(text, limit=limit, rerank=rerank)
    ranked_ids = [item.document_id for item in evidence if item.document_id]
    return first_relevant_rank(ranked_ids, question.expected)


def run_dataset(
    questions: list[EvalQuestion], limit: int, rerank: bool, rewrite: bool = False
) -> list[int | None]:
    ranks: list[int | None] = []
    for question in questions:
        rank = run_question(question, limit=limit, rerank=rerank, rewrite=rewrite)
        ranks.append(rank)
        print(f"  {question.id:<32} {'miss' if rank is None else f'rank {rank}'}", flush=True)
    return ranks


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=10, help="results per query (default 10)")
    parser.add_argument("--no-rerank", action="store_true", help="disable cross-encoder reranking")
    parser.add_argument("--dataset", type=str, default=None, help="path to a dataset JSON file")
    parser.add_argument(
        "--rewrite", action="store_true", help="rewrite each question with an LLM first"
    )
    args = parser.parse_args()

    questions = load_questions(Path(args.dataset) if args.dataset else None)
    rerank = not args.no_rerank

    print(
        f"{len(questions)} questions, limit={args.limit}, "
        f"rerank={rerank}, rewrite={args.rewrite}\n"
    )
    ranks = run_dataset(questions, limit=args.limit, rerank=rerank, rewrite=args.rewrite)

    print(
        f"\nMRR        {mean_reciprocal_rank(ranks):.3f}"
        f"\nrecall@1   {recall_at_k(ranks, 1):.0%}"
        f"\nrecall@5   {recall_at_k(ranks, 5):.0%}"
        f"\nrecall@10  {recall_at_k(ranks, 10):.0%}"
    )


if __name__ == "__main__":
    main()
