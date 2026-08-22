import pytest

from legal_ai.llm import client as llm


class _FakeModels:
    def __init__(self, behaviour):
        self.behaviour = behaviour
        self.calls = []

    def generate_content(self, model, contents):
        self.calls.append(model)
        outcome = self.behaviour.get(model, "ok")
        if outcome != "ok":
            raise RuntimeError(outcome)
        return type("R", (), {"text": f"answer from {model}"})()


@pytest.fixture
def fake(monkeypatch):
    def build(behaviour):
        models = _FakeModels(behaviour)
        monkeypatch.setattr(llm, "_client", lambda: type("C", (), {"models": models})())
        return models

    return build


def test_uses_the_first_model_when_it_works(fake):
    models = fake({})
    assert llm.generate("hi", chain=("a", "b")) == "answer from a"
    assert models.calls == ["a"]


def test_quota_exhaustion_moves_on_without_retrying(fake):
    # Retrying a 429 is what destroys the remaining daily budget.
    models = fake({"a": "429 RESOURCE_EXHAUSTED"})
    assert llm.generate("hi", chain=("a", "b")) == "answer from b"
    assert models.calls == ["a", "b"]


def test_a_retired_model_moves_on_without_retrying(fake):
    models = fake({"a": "404 NOT_FOUND"})
    assert llm.generate("hi", chain=("a", "b")) == "answer from b"
    assert models.calls == ["a", "b"]


def test_transient_overload_retries_the_same_model_first(fake, monkeypatch):
    monkeypatch.setattr(llm.time, "sleep", lambda _s: None)
    models = fake({"a": "503 UNAVAILABLE"})
    assert llm.generate("hi", chain=("a", "b")) == "answer from b"
    # Retried "a" up to the limit before falling through.
    assert models.calls == ["a"] * llm.MAX_RETRIES_PER_MODEL + ["b"]


def test_every_model_failing_raises_with_the_reason_per_model(fake):
    fake({"a": "429 RESOURCE_EXHAUSTED", "b": "404 NOT_FOUND"})
    with pytest.raises(llm.AllModelsUnavailable) as excinfo:
        llm.generate("hi", chain=("a", "b"))
    message = str(excinfo.value)
    assert "exhausted" in message and "missing" in message


def test_classifies_the_three_failure_modes_distinctly():
    assert llm._classify(RuntimeError("429 RESOURCE_EXHAUSTED")) == "exhausted"
    assert llm._classify(RuntimeError("404 NOT_FOUND")) == "missing"
    assert llm._classify(RuntimeError("503 UNAVAILABLE")) == "transient"
    assert llm._classify(RuntimeError("connection reset")) == "other"


def test_an_unclassified_error_does_not_retry_the_same_model(fake):
    models = fake({"a": "connection reset"})
    assert llm.generate("hi", chain=("a", "b")) == "answer from b"
    assert models.calls == ["a", "b"]


def test_chain_contains_only_models_verified_against_the_live_api():
    assert "gemini-2.5-flash" not in llm.MODEL_CHAIN
    assert "gemini-flash-latest" in llm.MODEL_CHAIN
    assert len(llm.MODEL_CHAIN) >= 5
