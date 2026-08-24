"""Measure contradiction detection: does the Case Agent find planted conflicts?

    .venv/bin/python -m evals.run_contradictions

The one Phase 4 output that can be graded objectively. Issues and missing
facts are the Case Agent's other model-written outputs, and neither has a
gradeable ground truth without an expert labelling every case -- "are these
the right issues?" is a judgement, and scoring it with another model
produces a number nobody can check. Contradictions do not have that
problem: a conflict is between two named documents, so a detection either
names both or it does not.

Read the two numbers together. Recall alone is worthless -- a detector that
cries conflict on every case scores 1.00 -- so the run is only meaningful
next to control precision, which is measured on cases whose documents
genuinely agree.

Documents are supplied as already-extracted structure, not files. That is
deliberate: this measures the Case Agent's cross-document reasoning, and
routing it through the Document Agent first would fold that agent's
extraction errors into a score meant to be about something else.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from evals.evaluators.contradictions import score, spurious
from evals.preflight import FailureTracker, require_model
from legal_ai.agents.case import analyse_case
from legal_ai.case.models import Case
from legal_ai.context.models import DocumentFacts
from legal_ai.llm.client import MODEL_USAGE, reset_model_usage

DATASET = Path(__file__).parent / "datasets" / "contradictions.json"


def _facts(raw: dict) -> DocumentFacts:
    return DocumentFacts(
        document_id=raw["document_id"],
        document_type=raw.get("document_type"),
        parties=tuple(raw.get("parties", ())),
        dates=tuple(raw.get("dates", ())),
        cited_sections=tuple(raw.get("cited_sections", ())),
        issues=tuple(raw.get("issues", ())),
        clauses=tuple(raw.get("clauses", ())),
        claims=tuple(raw.get("claims", ())),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=0, help="first N cases only")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    require_model()
    reset_model_usage()
    tracker = FailureTracker()

    cases = json.loads(DATASET.read_text())
    if args.limit:
        cases = cases[: args.limit]

    results: list[tuple[tuple[str, ...], list[tuple[str, str]]]] = []
    for entry in cases:
        meta = entry.get("case", {})
        case = Case(
            case_id=entry["id"],
            title=meta.get("title", entry["id"]),
            court=meta.get("court"),
            state=meta.get("state"),
        )
        documents = tuple(_facts(raw) for raw in entry["documents"])
        analysis = analyse_case(case, documents, [])
        tracker.record_model_failures()

        planted = [tuple(pair) for pair in entry["contradictions"]]
        results.append((analysis.contradictions, planted))

        control = " (control)" if not planted else ""
        found = len(
            [p for p in planted if all(d in t for t in analysis.contradictions for d in p)]
        )
        print(f"{entry['id']}{control}: reported {len(analysis.contradictions)}, planted {len(planted)}")
        if args.verbose:
            for text in analysis.contradictions:
                mark = "  ?" if text in spurious(analysis.contradictions, planted) else "  +"
                print(f"{mark} {text}")

    final = score(results)
    print()
    print(f"planted conflicts   {final.planted}")
    print(f"detected            {final.found}   recall {final.recall:.2f}")
    print(f"false alarms        {final.false_alarms}")
    print(f"controls left clean {final.controls_clean}/{final.controls}   "
          f"precision {final.control_precision:.2f}")
    print(f"models used         {dict(MODEL_USAGE)}")
    print()
    print("Recall without control precision means nothing -- a detector that")
    print("reports a conflict every time scores 1.00 recall.")


if __name__ == "__main__":
    main()
