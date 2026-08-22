"""An eval that cannot reach a model must fail, not report a low score.

Learned 2026-08-21: a multi-angle run reported 5% coverage against a 22%
control. The design under test had not changed -- the model chain had hit
its daily cap partway through. Questions on the identical code path scored
67% then 0%. A number like that gets written down and believed.
"""

import pytest

from evals import preflight
from legal_ai.llm.client import AllModelsUnavailable


def test_require_model_passes_when_a_model_answers(monkeypatch):
    monkeypatch.setattr(preflight, "generate", lambda prompt: "ok")
    assert preflight.require_model() == "ok"


def test_require_model_refuses_to_start_when_every_model_is_exhausted(monkeypatch):
    def exhausted(prompt):
        raise AllModelsUnavailable("all 8 models failed: quota")

    monkeypatch.setattr(preflight, "generate", exhausted)
    with pytest.raises(preflight.EvalPreconditionFailed) as excinfo:
        preflight.require_model()
    assert "measure API availability" in str(excinfo.value)


def test_a_few_failures_are_tolerated():
    tracker = preflight.FailureTracker(tolerance=0.2)
    for _ in range(9):
        tracker.record(failed=False)
    tracker.record(failed=True)  # 1 in 10, within tolerance


def test_a_run_aborts_once_most_questions_cannot_reach_a_model():
    tracker = preflight.FailureTracker(tolerance=0.2)
    with pytest.raises(preflight.EvalPreconditionFailed):
        for _ in range(5):
            tracker.record(failed=True)


def test_the_tracker_waits_for_a_meaningful_sample_before_aborting():
    # One early failure must not abort a run that is otherwise healthy.
    tracker = preflight.FailureTracker(tolerance=0.2)
    tracker.record(failed=True)
    tracker.record(failed=False)
    tracker.record(failed=False)
    assert tracker.failures == 1


def test_the_abort_message_says_what_to_do():
    tracker = preflight.FailureTracker(tolerance=0.0)
    with pytest.raises(preflight.EvalPreconditionFailed) as excinfo:
        for _ in range(5):
            tracker.record(failed=True)
    assert "Re-run when quota resets" in str(excinfo.value)


def test_a_question_that_found_nothing_is_not_counted_as_an_api_failure(monkeypatch):
    # An agent that searched and came up empty is a research result. Counting
    # it as unreachable would abort a run that is working correctly -- which
    # is what happened on the first fan-out measurement.
    from legal_ai.llm import client

    monkeypatch.setattr(client, "UNAVAILABLE_COUNT", 0)
    tracker = preflight.FailureTracker(tolerance=0.0)
    for _ in range(10):
        tracker.record_model_failures()
    assert tracker.failures == 0


def test_a_real_chain_failure_is_counted(monkeypatch):
    from legal_ai.llm import client

    tracker = preflight.FailureTracker(tolerance=0.9)
    monkeypatch.setattr(client, "UNAVAILABLE_COUNT", 0)
    tracker.record_model_failures()
    monkeypatch.setattr(client, "UNAVAILABLE_COUNT", 1)
    tracker.record_model_failures()
    assert tracker.failures == 1
