"""Score the rewriter against multi-turn threads.

    .venv/bin/python -m evals.run_conversation

Each case is a short conversation plus a follow-up that means nothing on its
own -- "what about bombay", "and the time limit to file". Two things are
measured:

  resolved    did the rewrite pull the referent in from the earlier turns
  preserved   did it keep what the user actually asked about

Both matter and they fail differently. A rewrite that drops the referent
retrieves the wrong law; one that drops the user's own words answers a
question they did not ask.

One case is already standalone. A rewriter that "improves" it is being
measured too -- leaving a complete question alone is part of the job.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from legal_ai.conversation.rewriter import Turn, rewrite_question
from legal_ai.conversation.router import Route, route_message

DATASET = Path(__file__).parent / "datasets" / "conversation.json"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--dataset", type=str, default=None)
    args = parser.parse_args()

    cases = json.loads(Path(args.dataset or DATASET).read_text())
    if args.limit:
        cases = cases[: args.limit]
    print(f"{len(cases)} cases\n")

    resolved = preserved = unchanged_ok = 0
    standalone_total = 0
    route_right = false_answer = false_research = 0

    for case in cases:
        history = [Turn(role, content) for role, content in case["history"]]
        rewritten = rewrite_question(case["message"], history)
        low = rewritten.lower()

        hit_resolve = (
            not case["must_resolve"]
            or any(token.lower() in low for token in case["must_resolve"])
        )
        hit_preserve = any(token.lower() in low for token in case["must_contain"])
        resolved += hit_resolve
        preserved += hit_preserve

        if not case["must_resolve"]:
            standalone_total += 1
            unchanged_ok += hit_preserve

        researched = route_message(case["message"], history) is Route.RESEARCH
        if researched == case["expects_research"]:
            route_right += 1
        elif case["expects_research"]:
            # Answered from memory a question that needed fresh law. The
            # dangerous direction: the user gets a confident wrong answer.
            false_answer += 1
            print(f"   ! answered from memory, needed research: {case['message']}")
        else:
            false_research += 1

        mark = "  " if (hit_resolve and hit_preserve) else "X "
        print(f"{mark}{case['id']:22} {rewritten[:88]}")

    n = max(len(cases), 1)
    print(f"\nresolved the referent   {resolved / n:.2f}  ({resolved}/{n})")
    print(f"preserved the question  {preserved / n:.2f}  ({preserved}/{n})")
    print(f"both                    {min(resolved, preserved) / n:.2f}")
    if standalone_total:
        print(f"standalone left intact  {unchanged_ok}/{standalone_total}")
    print(f"route correct           {route_right / n:.2f}  ({route_right}/{n})")
    print(f"  answered from memory when research was needed : {false_answer}"
          f"   <- the dangerous direction")
    print(f"  researched when memory would do               : {false_research}"
          f"   <- only slow")


if __name__ == "__main__":
    main()
