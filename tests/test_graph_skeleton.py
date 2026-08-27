import json
from pathlib import Path

from langgraph.checkpoint.memory import MemorySaver

from legal_ai.graph.build import build_research_graph
from legal_ai.graph.configuration import DEFAULT_CONFIG, GraphConfig
from legal_ai.graph.state import ResearchState


def test_graph_compiles_and_runs_end_to_end():
    result = build_research_graph().invoke({"question": "what is the punishment for murder"})
    assert result["answer"]


def test_context_is_built_once_and_lands_on_the_channel():
    result = build_research_graph().invoke({"question": "possession delay in Gujarat"})
    assert result["context"].revision == 1
    assert result["context"].jurisdiction.court == "Gujarat High Court"


def test_case_id_reaches_the_context():
    result = build_research_graph().invoke(
        {"question": "what are my options", "case_id": "case-patel-v-shah"}
    )
    assert result["context"].case_id == "case-patel-v-shah"


def test_a_thread_without_a_case_still_runs():
    result = build_research_graph().invoke({"question": "doctrine of frustration"})
    assert result["context"].case_id is None
    assert result["answer"]


def test_the_verification_loop_is_bounded_and_terminates():
    """The loop-back must be capped, not absent.

    This asserted `research_rounds == 1` on the theory that nothing
    produced claims, which was true before Phase 5 added the Analyst.
    The Analyst now produces claims on every run, so a claim whose
    citation does not survive groundedness legitimately sends the graph
    back to research -- a real run has been observed at 2 rounds and at 1.
    Because the round count depends on what the model writes, asserting an
    exact number tests the model, not the graph.

    What the graph actually guarantees, and what this now checks: the loop
    is capped, and the run always ships an answer.
    """
    config = DEFAULT_CONFIG
    result = build_research_graph().invoke({"question": "what is extortion"})

    assert 1 <= result["verification_passes"] <= config.max_verification_passes
    assert 1 <= result["research_rounds"] <= config.max_verification_passes
    assert result["answer"]


def test_clarification_halts_the_run_before_research(monkeypatch):
    from legal_ai.graph import nodes

    monkeypatch.setattr(nodes, "clarification", lambda state: {"clarification_needed": "which state?"})
    result = build_research_graph().invoke({"question": "builder took my money"})
    assert result["clarification_needed"] == "which state?"
    assert "answer" not in result or result.get("answer") is None


def test_findings_from_parallel_agents_concatenate_rather_than_overwrite():
    # Parallel research agents write the same channel; replacement would
    # silently drop whichever finished first.
    annotations = ResearchState.__annotations__["findings"]
    assert "add" in str(annotations)


def test_caps_are_configuration_not_prompt_text():
    assert DEFAULT_CONFIG.max_concurrent_research_units == 3
    assert DEFAULT_CONFIG.max_researcher_iterations == 3
    assert DEFAULT_CONFIG.max_plan_steps == 8
    assert DEFAULT_CONFIG.max_verification_passes == 2


def test_a_custom_config_is_honoured():
    graph = build_research_graph(GraphConfig(max_verification_passes=1))
    assert graph.invoke({"question": "what is theft"})["answer"]


def test_a_checkpointer_lets_a_thread_be_resumed():
    graph = build_research_graph(checkpointer=MemorySaver())
    config = {"configurable": {"thread_id": "t-1"}}
    graph.invoke({"question": "what is the punishment for murder"}, config)
    assert graph.get_state(config).values["context"].question


def test_langgraph_json_points_at_a_real_graph():
    manifest = json.loads(Path("langgraph.json").read_text())
    target = manifest["graphs"]["Legal Research"]
    path, attribute = target.split(":")
    assert Path(path.lstrip("./")).exists()
    from legal_ai.graph import build

    assert hasattr(build, attribute)
