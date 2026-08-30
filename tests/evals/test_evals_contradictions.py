"""The contradiction evaluator. Graded on document ids, never on prose."""

import json
from pathlib import Path

from evals.evaluators.contradictions import detected_pairs, score, spurious

DATASET = Path("evals/datasets/contradictions.json")


def test_a_detection_must_name_both_documents():
    # Naming one side is not finding the conflict -- "doc-1 looks wrong"
    # says nothing about what it conflicts with.
    assert detected_pairs(("doc-1 is suspicious",), [("doc-1", "doc-2")]) == set()
    assert detected_pairs(("doc-1 conflicts with doc-2",), [("doc-1", "doc-2")]) == {("doc-1", "doc-2")}


def test_wording_does_not_affect_the_score():
    # Grading prose against prose is a judgement call, and scoring a model
    # with a model gives a number nobody can check.
    for phrasing in (
        "doc-1 and doc-2 disagree about the possession date",
        "the term in doc-2 cannot stand with doc-1",
        "[doc-1] [doc-2]",
    ):
        assert detected_pairs((phrasing,), [("doc-1", "doc-2")])


def test_a_report_matching_no_planted_pair_is_spurious():
    assert spurious(("doc-3 conflicts with doc-4",), [("doc-1", "doc-2")])


def test_every_report_on_a_control_is_spurious():
    assert len(spurious(("doc-1 conflicts with doc-2",), [])) == 1


def test_always_reporting_a_conflict_scores_perfect_recall_and_fails_precision():
    # The whole reason controls exist. Recall alone cannot tell an eager
    # detector from a useful one.
    eager = [
        (("doc-1 conflicts with doc-2",), [("doc-1", "doc-2")]),
        (("doc-1 conflicts with doc-2",), []),
        (("doc-1 conflicts with doc-2",), []),
    ]
    result = score(eager)
    assert result.recall == 1.0
    assert result.control_precision == 0.0


def test_a_silent_detector_scores_zero_recall_and_perfect_precision():
    silent = [((), [("doc-1", "doc-2")]), ((), []), ((), [])]
    result = score(silent)
    assert result.recall == 0.0
    assert result.control_precision == 1.0


def test_a_perfect_run_scores_one_on_both():
    perfect = [(("doc-1 vs doc-2",), [("doc-1", "doc-2")]), ((), []), ((), [])]
    result = score(perfect)
    assert result.recall == 1.0
    assert result.control_precision == 1.0


def test_recall_is_one_when_nothing_was_planted():
    assert score([((), [])]).recall == 1.0


# --- the dataset itself ---

def test_the_dataset_has_negative_controls():
    # Without them the run cannot distinguish a detector from a yes-man.
    cases = json.loads(DATASET.read_text())
    controls = [c for c in cases if not c["contradictions"]]
    assert len(controls) >= 3


def test_every_planted_pair_names_documents_that_exist():
    # A pair naming a missing document would be unfindable, and the run
    # would report a detector failure that no code change could fix.
    for case in json.loads(DATASET.read_text()):
        ids = {d["document_id"] for d in case["documents"]}
        for pair in case["contradictions"]:
            assert set(pair) <= ids, f"{case['id']}: {pair} not in {ids}"


def test_every_case_has_at_least_two_documents():
    # A conflict needs two sides; a single-document case can neither carry
    # a planted conflict nor serve as a control for one.
    for case in json.loads(DATASET.read_text()):
        assert len(case["documents"]) >= 2, case["id"]


def test_every_case_carries_a_note_explaining_the_ground_truth():
    for case in json.loads(DATASET.read_text()):
        assert case.get("note"), case["id"]


def test_the_dataset_is_large_enough_to_tune_against():
    # At five planted conflicts, recall moved in steps of 0.20 -- no prompt
    # change could be told apart from one-case noise. That is the mistake
    # PHASE_3 §8a records about the 0.670 MRR figure, and this is the guard
    # against repeating it here.
    cases = json.loads(DATASET.read_text())
    planted = sum(len(c["contradictions"]) for c in cases)
    assert planted >= 15, f"only {planted} planted conflicts; a 1-case swing moves recall too far"


def test_controls_are_a_meaningful_share_of_the_set():
    # Recall alone rewards a detector that always says yes. The controls
    # have to be numerous enough that precision can actually fall.
    cases = json.loads(DATASET.read_text())
    controls = [c for c in cases if not c["contradictions"]]
    assert len(controls) >= len(cases) // 4


def test_the_set_covers_date_and_value_conflicts():
    # Gemini flash found only conflicts stated as plain negation and missed
    # every one needing a date or an amount compared across documents. The
    # set has to contain enough of those to measure that difference.
    cases = json.loads(DATASET.read_text())
    text = json.dumps(cases).lower()
    assert text.count("date") >= 5
    assert text.count("rs ") >= 8


def test_a_case_with_three_documents_exists():
    # Two-document cases make the pair trivially guessable: name both and
    # score. A third document that conflicts with neither tests whether the
    # detector actually identifies WHICH two disagree.
    cases = json.loads(DATASET.read_text())
    assert any(len(c["documents"]) >= 3 for c in cases)


def test_controls_include_a_superseding_amendment():
    # A supplementary agreement that expressly varies a date is a variation,
    # not a contradiction. Flagging it would make the feature noise on every
    # real file, since amended terms are ordinary.
    cases = json.loads(DATASET.read_text())
    assert any("supplementary" in json.dumps(c).lower() for c in cases if not c["contradictions"])
