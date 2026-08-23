import pytest

from legal_ai.llm import client as llm


class _FakeModels:
    def __init__(self, behaviour):
        self.behaviour = behaviour
        self.calls = []

    def generate_content(self, model, contents, config=None):
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


def test_rate_limiting_backs_off_once_then_moves_on(fake, monkeypatch):
    # A 429 is two failures wearing one code: a per-minute limit, which
    # clears in seconds, and a daily cap, which does not. One backoff
    # distinguishes them cheaply; retrying harder destroys a daily budget.
    monkeypatch.setattr(llm.time, "sleep", lambda _s: None)
    models = fake({"a": "429 RESOURCE_EXHAUSTED"})
    assert llm.generate("hi", chain=("a", "b")) == "answer from b"
    assert models.calls == ["a", "a", "b"]


def test_a_rate_limit_that_clears_is_served_by_the_same_model(fake, monkeypatch):
    monkeypatch.setattr(llm.time, "sleep", lambda _s: None)
    models = fake({"a": "429 RESOURCE_EXHAUSTED"})

    original = models.generate_content

    def clears_after_first(model, contents, config=None):
        if models.calls.count("a") >= 1:
            models.behaviour.pop("a", None)
        return original(model, contents)

    models.generate_content = clears_after_first
    assert llm.generate("hi", chain=("a", "b")) == "answer from a"


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


def test_the_model_that_answered_is_recorded(fake):
    # A benchmark that falls through the chain partway is not one
    # measurement: later questions were answered by a weaker model than
    # earlier ones, and the score blends them. Recording this makes it
    # visible rather than silent.
    llm.reset_model_usage()
    fake({"a": "429 RESOURCE_EXHAUSTED"})
    llm.generate("hi", chain=("a", "b"))
    assert llm.MODEL_USAGE == {"b": 1}


def test_repeated_calls_accumulate_per_model(fake):
    llm.reset_model_usage()
    fake({})
    for _ in range(3):
        llm.generate("hi", chain=("a", "b"))
    assert llm.MODEL_USAGE == {"a": 3}
