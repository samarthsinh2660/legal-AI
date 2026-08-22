# Phase 3 Milestone 6a — Evaluation Harness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a rerunnable evaluation harness that measures whether a search returns the correct legal provision, so retrieval and (later) agent changes can be judged by number instead of opinion.

**Architecture:** Three layers with a hard separation. Pure metric functions operate on ranked id lists and touch nothing else, so they unit-test in milliseconds. A JSON dataset maps a question to the document ids that correctly answer it. A runner joins the two by calling the existing Phase 2 `hybrid_search` and printing a table. The measuring instrument is testable independently of what it measures — that is the whole point of the split.

**Tech Stack:** Python 3.11+, pytest, stdlib `json`/`dataclasses`/`argparse`. No new dependencies. Reads the existing Postgres corpus via `legal_ai.knowledge.static.db.get_connection`.

## Global Constraints

- No new third-party dependencies. `json` and `dataclasses` are stdlib; do not add PyYAML.
- `evals/` lives at the repo root, not under `src/`. It is a measurement tool, never imported by `src/legal_ai/` production code.
- Zero changes to `src/legal_ai/retrieval/`. This milestone measures Phase 2; it does not modify it.
- The full existing suite (159 tests) must still pass after every task.
- Run everything with the project venv: `.venv/bin/python`, `.venv/bin/python -m pytest`.
- Document ids are real and verifiable. Sections are `act:{act_id}:sec-{number}`; judgments are `judgment:{source}-{id}`. Never invent one — every id in a dataset must resolve to a row in `documents`.
- Corpus today: 35,601 sections, 860 acts, **6 judgments**. Questions must therefore target sections; a judgment-answer question would be unanswerable and would measure corpus coverage rather than retrieval.
- Per user standing rule: **do not run `git commit`, `git add`, or `git push`.** Commit steps below are written for the user to run themselves.

---

## File Structure

| File | Responsibility |
|---|---|
| `evals/__init__.py` | package marker |
| `evals/evaluators/__init__.py` | package marker |
| `evals/evaluators/ranking.py` | pure metrics: rank of first correct answer, MRR, recall@k. No DB, no model, no I/O. |
| `evals/dataset.py` | `EvalQuestion` dataclass + JSON loader |
| `evals/datasets/retrieval.json` | the questions and their correct document ids |
| `evals/run.py` | CLI: run the dataset through `hybrid_search`, print the results table |
| `tests/test_evals_ranking.py` | metric tests — pure, fast, no DB |
| `tests/test_evals_dataset.py` | loader tests + every expected id resolves to a real document |

`evals/` is importable from tests without packaging changes: `tests/__init__.py` exists, so pytest walks up to the first directory without one — the repo root — and puts that on `sys.path`.

---

### Task 1: Ranking metrics

Pure functions over ranked id lists. Built first and tested alone, because a measuring instrument that is itself unverified is worse than none.

**Files:**
- Create: `evals/__init__.py` (empty)
- Create: `evals/evaluators/__init__.py` (empty)
- Create: `evals/evaluators/ranking.py`
- Test: `tests/test_evals_ranking.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `first_relevant_rank(ranked_ids: list[str], expected_ids: Iterable[str]) -> int | None` — 1-based rank of the earliest id in `ranked_ids` that appears in `expected_ids`; `None` if none do.
  - `mean_reciprocal_rank(ranks: Iterable[int | None]) -> float`
  - `recall_at_k(ranks: Iterable[int | None], k: int) -> float` — fraction of questions whose rank is present and `<= k`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_evals_ranking.py
import pytest

from evals.evaluators.ranking import first_relevant_rank, mean_reciprocal_rank, recall_at_k


def test_first_relevant_rank_is_one_based():
    # Rank 1 means "top hit", not "index 0" -- MRR of a top hit must be 1.0.
    assert first_relevant_rank(["a", "b", "c"], {"a"}) == 1
    assert first_relevant_rank(["a", "b", "c"], {"c"}) == 3


def test_first_relevant_rank_is_none_when_absent():
    assert first_relevant_rank(["a", "b"], {"z"}) is None


def test_first_relevant_rank_takes_the_earliest_of_several_correct_answers():
    # Some questions have more than one right answer (near-duplicate
    # provisions across Acts); credit the best-ranked one.
    assert first_relevant_rank(["a", "b", "c"], {"c", "b"}) == 2


def test_first_relevant_rank_of_empty_results_is_none():
    assert first_relevant_rank([], {"a"}) is None


def test_mean_reciprocal_rank_averages_inverse_ranks():
    # 1/1 + 1/2 + 1/4 over three questions.
    assert mean_reciprocal_rank([1, 2, 4]) == pytest.approx((1 + 0.5 + 0.25) / 3)


def test_mean_reciprocal_rank_scores_a_miss_as_zero():
    assert mean_reciprocal_rank([1, None]) == pytest.approx(0.5)


def test_mean_reciprocal_rank_of_nothing_is_zero():
    assert mean_reciprocal_rank([]) == 0.0


def test_recall_at_k_counts_ranks_within_k():
    assert recall_at_k([1, 3, 11, None], k=5) == pytest.approx(0.5)


def test_recall_at_k_boundary_is_inclusive():
    assert recall_at_k([5], k=5) == 1.0
    assert recall_at_k([6], k=5) == 0.0


def test_recall_at_k_of_nothing_is_zero():
    assert recall_at_k([], k=10) == 0.0
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_evals_ranking.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'evals'`

- [ ] **Step 3: Write the implementation**

```python
# evals/evaluators/ranking.py
"""Ranking metrics -- pure functions over ranked document-id lists.

Deliberately free of database, model and file access so they can be tested
directly. A measuring instrument that cannot itself be verified is worse
than no instrument, because its numbers still get believed.

A rank is 1-based; None means the correct answer was not returned at all.
"""

from __future__ import annotations

from typing import Iterable, Optional


def first_relevant_rank(ranked_ids: list[str], expected_ids: Iterable[str]) -> Optional[int]:
    """1-based rank of the earliest correct answer, or None if absent.

    A question may have several correct answers -- near-duplicate provisions
    exist across Acts -- and the best-ranked one is what counts.
    """
    expected = set(expected_ids)
    for rank, document_id in enumerate(ranked_ids, start=1):
        if document_id in expected:
            return rank
    return None


def mean_reciprocal_rank(ranks: Iterable[int | None]) -> float:
    """Mean of 1/rank, scoring a miss as 0.

    MRR is dominated by the top few positions: rank 1 scores 1.0 while rank
    10 scores 0.1. It answers "is the right answer at the top", which is a
    different question from recall@k's "is it in the list at all".
    """
    values = list(ranks)
    if not values:
        return 0.0
    return sum(0.0 if rank is None else 1.0 / rank for rank in values) / len(values)


def recall_at_k(ranks: Iterable[int | None], k: int) -> float:
    """Fraction of questions whose correct answer landed in the top k."""
    values = list(ranks)
    if not values:
        return 0.0
    return sum(1 for rank in values if rank is not None and rank <= k) / len(values)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_evals_ranking.py -v`
Expected: PASS — 9 passed

- [ ] **Step 5: Commit** (user runs this)

```bash
git add evals/__init__.py evals/evaluators/ tests/test_evals_ranking.py
git commit -m "add ranking metrics for the eval harness"
```

---

### Task 2: Dataset and loader

**Files:**
- Create: `evals/dataset.py`
- Create: `evals/datasets/retrieval.json`
- Test: `tests/test_evals_dataset.py`

**Interfaces:**
- Consumes: nothing from Task 1.
- Produces:
  - `EvalQuestion` — frozen dataclass with `id: str`, `question: str`, `expected: tuple[str, ...]`, `note: str`.
  - `load_questions(path: Path | None = None) -> list[EvalQuestion]` — defaults to `evals/datasets/retrieval.json`.
  - `DEFAULT_DATASET: Path`

**Note on ground truth:** every `expected` id below was verified against the live corpus by reading the section title, not by pattern-matching. Pattern matching is unsafe here — searching titles for "cheating" returns *Cheating at games and gambling in street*, and for "right to information" returns an institute's public-authority clause. A wrong label makes the benchmark lie in the direction of looking broken.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_evals_dataset.py
import pytest

from evals.dataset import DEFAULT_DATASET, EvalQuestion, load_questions
from legal_ai.knowledge.static.db import get_connection


def test_loads_the_default_dataset():
    questions = load_questions()
    assert len(questions) >= 13
    assert all(isinstance(q, EvalQuestion) for q in questions)


def test_every_question_has_text_and_at_least_one_expected_id():
    for question in load_questions():
        assert question.question.strip(), f"{question.id} has no question text"
        assert question.expected, f"{question.id} has no expected answer"


def test_question_ids_are_unique():
    ids = [q.id for q in load_questions()]
    assert len(ids) == len(set(ids))


def test_expected_ids_all_resolve_to_real_documents():
    # The single most important test in the harness. An expected id that
    # does not exist can never be retrieved, so the benchmark would report
    # a permanent, unfixable failure and blame retrieval for it.
    expected = {doc_id for q in load_questions() for doc_id in q.expected}
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT document_id FROM documents WHERE document_id = ANY(%s)",
                (list(expected),),
            )
            found = {row[0] for row in cur.fetchall()}
    finally:
        conn.close()
    assert expected - found == set(), f"dataset references missing documents: {expected - found}"


def test_dataset_file_is_where_the_loader_expects():
    assert DEFAULT_DATASET.exists()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_evals_dataset.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'evals.dataset'`

- [ ] **Step 3: Write the dataset file**

```json
[
  {
    "id": "rera-possession-refund",
    "question": "builder failed to give possession of my flat on time, can I get a refund",
    "expected": ["act:2158:sec-18"],
    "note": "RERA s.18 - Return of amount and compensation"
  },
  {
    "id": "rera-project-registration",
    "question": "does a builder have to register the housing project before selling flats",
    "expected": ["act:2158:sec-3"],
    "note": "RERA s.3 - Prior registration of real estate project"
  },
  {
    "id": "rera-registration-application",
    "question": "how does a promoter apply to register a real estate project",
    "expected": ["act:2158:sec-4"],
    "note": "RERA s.4 - Application for registration"
  },
  {
    "id": "cheque-bounce",
    "question": "the cheque I received bounced due to insufficient funds, what is the offence",
    "expected": ["act:2189:sec-138"],
    "note": "NI Act s.138 - Dishonour of cheque"
  },
  {
    "id": "restraint-of-trade",
    "question": "my employment contract stops me joining a competitor after I leave",
    "expected": ["act:2187:sec-27"],
    "note": "Contract Act s.27 - Agreement in restraint of trade, void"
  },
  {
    "id": "free-consent-defined",
    "question": "what does free consent mean in a contract",
    "expected": ["act:2187:sec-14"],
    "note": "Contract Act s.14 - Free consent defined"
  },
  {
    "id": "consent-voidability",
    "question": "I signed the agreement under pressure, is it still binding",
    "expected": ["act:2187:sec-19"],
    "note": "Contract Act s.19 - Voidability of agreements without free consent"
  },
  {
    "id": "bailment-defined",
    "question": "I gave my goods to someone for safekeeping, what is that relationship called",
    "expected": ["act:2187:sec-148"],
    "note": "Contract Act s.148 - Bailment, bailor and bailee defined"
  },
  {
    "id": "murder-punishment",
    "question": "what is the punishment for murder",
    "expected": ["act:20062:sec-103"],
    "note": "BNS s.103 - Punishment for murder"
  },
  {
    "id": "rape-punishment",
    "question": "what punishment does the law prescribe for rape",
    "expected": ["act:20062:sec-64"],
    "note": "BNS s.64 - Punishment for rape"
  },
  {
    "id": "grievous-hurt",
    "question": "what injuries count as grievous hurt",
    "expected": ["act:20062:sec-116"],
    "note": "BNS s.116 - Grievous hurt"
  },
  {
    "id": "criminal-breach-of-trust",
    "question": "someone I entrusted money to has misappropriated it",
    "expected": ["act:20062:sec-316"],
    "note": "BNS s.316 - Criminal breach of trust"
  },
  {
    "id": "maintenance-wife-children",
    "question": "my husband has stopped supporting me and the children, can I claim maintenance",
    "expected": ["act:20099:sec-144"],
    "note": "BNSS s.144 - Order for maintenance of wives, children and parents"
  },
  {
    "id": "consumer-district-commission",
    "question": "which forum hears a consumer complaint at the district level",
    "expected": ["act:15256:sec-28"],
    "note": "Consumer Protection Act s.28 - District Consumer Disputes Redressal Commission"
  }
]
```

- [ ] **Step 4: Write the loader**

```python
# evals/dataset.py
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


@dataclass(frozen=True)
class EvalQuestion:
    id: str
    question: str
    # Several ids because near-duplicate provisions exist across Acts;
    # retrieving any one of them is a correct answer.
    expected: tuple[str, ...]
    note: str = ""


def load_questions(path: Path | None = None) -> list[EvalQuestion]:
    raw = json.loads((path or DEFAULT_DATASET).read_text())
    return [
        EvalQuestion(
            id=item["id"],
            question=item["question"],
            expected=tuple(item["expected"]),
            note=item.get("note", ""),
        )
        for item in raw
    ]
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_evals_dataset.py -v`
Expected: PASS — 5 passed. If `test_expected_ids_all_resolve_to_real_documents` fails, the named id is wrong in the JSON — fix the dataset, never the test.

- [ ] **Step 6: Commit** (user runs this)

```bash
git add evals/dataset.py evals/datasets/retrieval.json tests/test_evals_dataset.py
git commit -m "add eval dataset and loader with ground-truth validation"
```

---

### Task 3: Runner, and the reranking comparison

**Files:**
- Create: `evals/run.py`

**Interfaces:**
- Consumes: `evals.dataset.load_questions`, `evals.dataset.EvalQuestion`, `evals.evaluators.ranking.{first_relevant_rank, mean_reciprocal_rank, recall_at_k}`, and `legal_ai.retrieval.hybrid.hybrid_search`.
- Produces:
  - `run_question(question: EvalQuestion, limit: int, rerank: bool) -> int | None`
  - `run_dataset(questions: list[EvalQuestion], limit: int, rerank: bool) -> list[int | None]`
  - `main() -> None` — argparse CLI.

**Why there is no unit test for `run.py`:** it is glue over two already-tested layers plus `hybrid_search`, which Phase 2's suite covers. A test here would either mock `hybrid_search` (asserting nothing real) or hit the full corpus (slow, and it is what Step 3 does by hand anyway).

- [ ] **Step 1: Write the runner**

```python
# evals/run.py
"""Run the evaluation dataset through Phase 2 retrieval and report metrics.

    .venv/bin/python -m evals.run
    .venv/bin/python -m evals.run --no-rerank
    .venv/bin/python -m evals.run --limit 20

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


def run_question(question: EvalQuestion, limit: int, rerank: bool) -> int | None:
    evidence = hybrid_search(question.question, limit=limit, rerank=rerank)
    ranked_ids = [item.document_id for item in evidence if item.document_id]
    return first_relevant_rank(ranked_ids, question.expected)


def run_dataset(questions: list[EvalQuestion], limit: int, rerank: bool) -> list[int | None]:
    ranks: list[int | None] = []
    for question in questions:
        rank = run_question(question, limit=limit, rerank=rerank)
        ranks.append(rank)
        print(f"  {question.id:<32} {'miss' if rank is None else f'rank {rank}'}")
    return ranks


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=10, help="results per query (default 10)")
    parser.add_argument("--no-rerank", action="store_true", help="disable cross-encoder reranking")
    parser.add_argument("--dataset", type=str, default=None, help="path to a dataset JSON file")
    args = parser.parse_args()

    questions = load_questions(Path(args.dataset) if args.dataset else None)
    rerank = not args.no_rerank

    print(f"{len(questions)} questions, limit={args.limit}, rerank={rerank}\n")
    ranks = run_dataset(questions, limit=args.limit, rerank=rerank)

    print(
        f"\nMRR        {mean_reciprocal_rank(ranks):.3f}"
        f"\nrecall@1   {recall_at_k(ranks, 1):.0%}"
        f"\nrecall@5   {recall_at_k(ranks, 5):.0%}"
        f"\nrecall@10  {recall_at_k(ranks, 10):.0%}"
    )


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run it with reranking on**

Run: `.venv/bin/python -m evals.run`
Expected: a per-question list then a metrics block. Takes a few minutes — roughly 2-3s per question on CPU. Record the four numbers.

- [ ] **Step 3: Run it with reranking off**

Run: `.venv/bin/python -m evals.run --no-rerank`
Expected: same shape, lower numbers. Record them.

- [ ] **Step 4: Compare against the Phase 2 claim**

`docs/phases/PHASE_2_QUERY_RETRIEVAL.md` lines 318-321 record, on a 15-query set that no longer exists in the repo:

| configuration | MRR | recall@1 | recall@5 | recall@10 |
|---|---|---|---|---|
| fan-in only | 0.299 | 13% | 67% | 73% |
| fan-in + rerank | 0.530 | 40% | 87% | 87% |

**Exact reproduction is not the acceptance criterion and must not be claimed.** The original questions were lost, so this is a different question set; identical numbers would be coincidence. What must hold is the *relationship* that justified turning reranking on:

- reranked MRR is substantially higher than un-reranked MRR
- reranked recall@5 is higher than un-reranked recall@5

If reranking does **not** win on this set, stop and investigate before continuing to 6b. Either the new questions are easier than the originals (reranking has less to fix), the ground truth is mislabelled, or the Phase 2 conclusion was wrong. Any of the three is worth knowing now.

- [ ] **Step 5: Record the result in the Phase 2 doc**

Add to `docs/phases/PHASE_2_QUERY_RETRIEVAL.md`, immediately after the table at line 321, a short block giving: the date, the command, the new question count, both sets of numbers, and one sentence stating that the original 15-query set was not preserved and these numbers come from a different, now-versioned set. Do not delete or edit the original table — it is the record of what was decided at the time.

- [ ] **Step 6: Run the full suite**

Run: `.venv/bin/python -m pytest -q`
Expected: 159 existing + 14 new = 173 passed

- [ ] **Step 7: Commit** (user runs this)

```bash
git add evals/run.py docs/phases/PHASE_2_QUERY_RETRIEVAL.md
git commit -m "add eval runner and record reproducible retrieval baseline"
```

---

### Task 4: Expand the question set

Fourteen questions is too few to judge retrieval and far too few to judge an agent — one question moves MRR by 7 points. Target 50.

**Files:**
- Modify: `evals/datasets/retrieval.json`

**Interfaces:**
- Consumes: `evals.dataset.load_questions`.
- Produces: no new code. The dataset grows; every other interface is unchanged.

- [ ] **Step 1: Raise the count assertion**

In `tests/test_evals_dataset.py`, change `assert len(questions) >= 13` to `assert len(questions) >= 50`.

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_evals_dataset.py::test_loads_the_default_dataset -v`
Expected: FAIL — assertion error showing the current count.

- [ ] **Step 3: Find candidate sections and verify each title**

For each new question, find the section and **read its title** before writing the label:

```bash
.venv/bin/python -c "
from legal_ai.knowledge.static.db import get_connection
c = get_connection()
with c.cursor() as cur:
    cur.execute(
        \"SELECT document_id, title FROM documents \"
        \"WHERE document_type='section' AND title ILIKE %s LIMIT 5\",
        ('%maintenance%',))
    for row in cur.fetchall():
        print(row)
c.close()"
```

Rules for a new entry:

- **Phrase the question the way a person would**, not the way the statute does. The statute says *promoter*; a user says *builder*. That vocabulary gap is exactly what the harness exists to measure — a question copied from the section title measures nothing.
- **Verify the title actually answers the question.** Title matching is unreliable: `%cheating%` returns *Cheating at games and gambling in street*.
- **Spread across Acts.** Aim for a mix of RERA, Contract, BNS, BNSS, Consumer Protection, NI Act, IT Act, and civil/property statutes, rather than many questions against one Act.
- **Include several questions that should be hard** — vocabulary mismatch, or an answer known to rank poorly. A benchmark of easy questions reports a healthy number and detects nothing.
- **Where two provisions genuinely both answer it, list both** in `expected`. The Contract Act s.27 case in `PHASE_2_QUERY_RETRIEVAL.md` line 185 is the known example: a near-duplicate exists, and labelling only one makes the harness report a miss where retrieval was right.
- **Do not add questions whose answer is a judgment.** The corpus holds 6.

**Verified candidate pool.** These ids were confirmed against the live corpus
by reading each title. Use them as a starting point — you still write the
*question* in a user's words, and you still confirm the section genuinely
answers it:

| document_id | title | Act |
|---|---|---|
| `act:2158:sec-11` | Functions and duties of promoter | RERA |
| `act:2158:sec-19` | Rights and duties of allottees | RERA |
| `act:2187:sec-31` | "Contingent contract" defined | Contract Act |
| `act:2187:sec-19` | Voidability of agreements without free consent | Contract Act |
| `act:2189:sec-95` | Party receiving must transmit notice of dishonour | NI Act |
| `act:2189:sec-106` | Reasonable time of giving notice of dishonour | NI Act |
| `act:20062:sec-356` | Defamation | BNS |
| `act:20062:sec-126` | Wrongful restraint | BNS |
| `act:20062:sec-104` | Punishment for murder by life-convict | BNS |
| `act:20062:sec-118` | Voluntarily causing hurt by dangerous weapons | BNS |
| `act:20099:sec-222` | Prosecution for defamation | BNSS |
| `act:15256:sec-42` | Establishment of State Consumer Disputes Redressal Commission | Consumer Protection |
| `act:15256:sec-83` | Product liability action | Consumer Protection |
| `act:15256:sec-87` | Exceptions to product liability action | Consumer Protection |
| `act:15256:sec-94` | Unfair trade practices in e-commerce, direct selling | Consumer Protection |
| `act:1999:sec-43A` | Compensation for failure to protect data | IT Act |
| `act:1999:sec-66C` | Punishment for identity theft | IT Act |
| `act:1999:sec-66D` | Cheating by personation using computer resource | IT Act |
| `act:1999:sec-66F` | Punishment for cyber terrorism | IT Act |
| `act:2390:sec-58` | Specific performance | (verify Act before use) |
| `act:2027:sec-24` | Restrictions of advertisement, unfair trade practices | (verify Act before use) |
| `act:20062:sec-65` | Punishment for rape in certain cases | BNS |

The last two are marked for verification because their parent Act was not
confirmed during planning; run the query in Step 3 against
`SELECT title FROM documents WHERE document_id = 'act:2390'` before using
them.

That is 22 verified ids toward the 36 still needed. Source the remainder the
same way.

- [ ] **Step 4: Run the dataset tests**

Run: `.venv/bin/python -m pytest tests/test_evals_dataset.py -v`
Expected: PASS — 5 passed. `test_expected_ids_all_resolve_to_real_documents` catches any typo'd id.

- [ ] **Step 5: Re-run the benchmark on the full set**

Run: `.venv/bin/python -m evals.run` then `.venv/bin/python -m evals.run --no-rerank`

Expected: numbers will differ from Task 3 — a larger, deliberately harder set should score **lower**. That is the benchmark working, not a regression. Update the block added in Task 3 Step 5 with the new counts and figures, and note that the earlier figures came from the 14-question set.

- [ ] **Step 6: Run the full suite**

Run: `.venv/bin/python -m pytest -q`
Expected: 173 passed

- [ ] **Step 7: Commit** (user runs this)

```bash
git add evals/datasets/retrieval.json tests/test_evals_dataset.py docs/phases/PHASE_2_QUERY_RETRIEVAL.md
git commit -m "expand eval dataset to 50 questions"
```

---

## What this milestone deliberately does not build

Per the spec's `evals/` tree (§9), these arrive with the agents that need them, not now:

- `evaluators/groundedness.py`, `citation_accuracy.py`, `structure.py` — nothing produces claims, citations or a `DraftAnswer` yet. Building an evaluator with nothing to evaluate is the speculation this project avoids.
- `datasets/hallucination/` — questions the corpus cannot answer, where declining is correct. Needs an agent that can decline; plain retrieval always returns its nearest match.
- LangSmith integration — no model calls to trace yet.
