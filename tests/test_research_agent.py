"""Milestone 7.1 -- plan, execute, validate, compress.

The central claim these tests defend: the LLM never calls a tool. A canned
plan must execute end to end with no model call at all.
"""

from datetime import datetime, timezone

import pytest

from legal_ai.agents import research as ra
from legal_ai.agents.executor import execute_plan, execute_step
from legal_ai.agents.planner import ALLOWED_TOOLS, Plan, PlanStep, parse_plan
from legal_ai.agents.validator import evidence_ids_survived, validate
from legal_ai.knowledge.static.db import get_connection
from legal_ai.schemas.evidence import Evidence, Provenance, SourceRef


def _evidence(doc_id="act:2158:sec-18", content="text", url="https://x"):
    return Evidence(
        content=content,
        document_id=doc_id,
        provenance=Provenance(
            source=SourceRef(name="India Code", url=url, source_type="primary"),
            retrieved_at=datetime(2026, 8, 21, tzinfo=timezone.utc),
            licence="GoI",
            attribution_required=False,
        ),
    )


# ---------------------------------------------------------------- planner

def test_parse_plan_accepts_a_well_formed_plan():
    plan = parse_plan('[{"tool": "search_statutes", "args": {"query": "promoter possession"}}]', 8)
    assert plan.steps[0].tool == "search_statutes"


def test_parse_plan_drops_a_tool_that_does_not_exist():
    # A hallucinated tool must never reach the executor.
    plan = parse_plan('[{"tool": "delete_everything", "args": {}}]', 8)
    assert plan.steps == ()


def test_parse_plan_drops_a_step_whose_args_are_not_an_object():
    assert parse_plan('[{"tool": "search_statutes", "args": "oops"}]', 8).steps == ()


def test_parse_plan_enforces_the_step_cap_even_if_the_model_ignores_it():
    raw = "[" + ",".join(['{"tool": "search_statutes", "args": {}}'] * 20) + "]"
    assert len(parse_plan(raw, max_steps=3).steps) == 3


def test_parse_plan_of_garbage_is_empty_not_an_exception():
    assert parse_plan("I'm sorry, I can't do that", 8).steps == ()
    assert parse_plan('{"not": "a list"}', 8).steps == ()


def test_parse_plan_handles_a_fenced_code_block():
    raw = '```json\n[{"tool": "get_section", "args": {"act_id": "act:2158", "section_number": "18"}}]\n```'
    assert parse_plan(raw, 8).steps[0].tool == "get_section"


def test_every_allowed_tool_is_actually_executable():
    from legal_ai.tools.registry import TOOLS

    # Every tool a plan may name must be bound in the registry. The registry
    # may hold more (get_statute is reachable by other callers).
    assert set(ALLOWED_TOOLS) <= set(TOOLS)


# --------------------------------------------------------------- executor

def test_a_canned_plan_executes_with_no_model_call(monkeypatch):
    # The whole point of plan-then-execute: control flow needs no LLM.
    def explode(*a, **k):
        raise AssertionError("the executor must not call a model")

    monkeypatch.setattr("legal_ai.llm.client.generate", explode)
    plan = Plan(steps=(PlanStep("search_statutes", {"query": "promoter possession refund"}),))
    assert execute_plan(plan)


def test_unknown_arguments_are_dropped_rather_than_failing_the_step():
    step = PlanStep("search_statutes", {"query": "possession refund", "temperature": 0.7})
    assert execute_step(step)


def test_a_failing_step_yields_nothing_instead_of_raising():
    assert execute_step(PlanStep("get_section", {"act_id": "nope", "section_number": "999"})) == []


def test_a_step_naming_an_unknown_tool_yields_nothing():
    assert execute_step(PlanStep("not_a_tool", {})) == []


def test_results_are_deduplicated_across_steps():
    plan = Plan(steps=(
        PlanStep("get_section", {"act_id": "act:2158", "section_number": "18"}),
        PlanStep("get_section", {"act_id": "act:2158", "section_number": "18"}),
    ))
    assert len({e.document_id for e in execute_plan(plan)}) == len(execute_plan(plan))


# -------------------------------------------------------------- validator

def test_evidence_without_a_document_id_is_dropped():
    result = validate([_evidence(doc_id=None)])
    assert result.kept == []
    assert result.dropped[0][1] == "no document_id"


def test_evidence_with_empty_content_is_dropped():
    result = validate([_evidence(content="   ")])
    assert result.dropped[0][1] == "empty content"


def test_evidence_without_a_provenance_url_is_dropped():
    result = validate([_evidence(url="")])
    assert result.dropped[0][1] == "no provenance url"


def test_an_id_that_does_not_resolve_is_dropped():
    conn = get_connection()
    try:
        result = validate([_evidence(doc_id="act:0:sec-nonexistent")], conn=conn)
    finally:
        conn.close()
    assert result.kept == []
    assert result.dropped[0][1] == "document_id does not resolve"


def test_a_real_id_survives_validation():
    conn = get_connection()
    try:
        result = validate([_evidence()], conn=conn)
    finally:
        conn.close()
    assert len(result.kept) == 1
    assert result.dropped == []


def test_all_dropped_is_reported_so_the_next_round_can_plan_around_it():
    result = validate([_evidence(doc_id=None)])
    assert result.all_dropped


# ------------------------------------------------------------- compression

def test_compression_appends_evidence_ids_structurally(monkeypatch):
    # The highest-risk failure in the phase: a summary that loses its ids
    # makes every downstream claim ungroundable. Appending them makes that
    # impossible rather than merely unlikely.
    monkeypatch.setattr(ra, "generate", lambda prompt: "A summary that mentions no identifiers.")
    summary = ra.compress("refund", [_evidence("act:2158:sec-18"), _evidence("act:2158:sec-19")])
    assert "act:2158:sec-18" in summary
    assert "act:2158:sec-19" in summary


def test_evidence_ids_survive_check_agrees_with_compression(monkeypatch):
    monkeypatch.setattr(ra, "generate", lambda prompt: "no ids here")
    evidence = [_evidence("act:2158:sec-18")]
    assert evidence_ids_survived(ra.compress("refund", evidence), evidence)


def test_compression_survives_a_model_failure(monkeypatch):
    monkeypatch.setattr(ra, "generate", lambda p: (_ for _ in ()).throw(RuntimeError("429")))
    summary = ra.compress("refund", [_evidence("act:2158:sec-18")])
    assert "act:2158:sec-18" in summary


def test_compression_of_nothing_says_so():
    assert "No supporting provisions" in ra.compress("refund", [])


# -------------------------------------------------------------- the loop

def test_the_loop_stops_when_the_model_says_sufficient(monkeypatch):
    monkeypatch.setattr(ra, "build_plan",
                        lambda *a, **k: Plan(steps=(PlanStep("search_statutes", {"query": "x"}),)))
    monkeypatch.setattr(ra, "execute_plan", lambda plan: [_evidence()])
    monkeypatch.setattr(ra, "generate", lambda prompt: "SUFFICIENT")
    assert ra.research_angle("refund", max_rounds=5).rounds == 1


def test_the_loop_terminates_on_the_cap_when_the_model_never_stops(monkeypatch):
    # The cap is the guarantee; the model's judgement is not.
    monkeypatch.setattr(ra, "build_plan",
                        lambda *a, **k: Plan(steps=(PlanStep("search_statutes", {"query": "x"}),)))
    monkeypatch.setattr(ra, "execute_plan", lambda plan: [_evidence()])
    monkeypatch.setattr(ra, "generate", lambda prompt: "still missing everything")
    assert ra.research_angle("refund", max_rounds=3).rounds == 3


def test_an_empty_plan_ends_the_round_rather_than_looping(monkeypatch):
    monkeypatch.setattr(ra, "build_plan", lambda *a, **k: Plan(steps=()))
    result = ra.research_angle("refund", max_rounds=3)
    assert result.rounds == 1
    assert result.evidence == []


def test_dropped_results_are_reported_on_the_finding(monkeypatch):
    monkeypatch.setattr(ra, "build_plan",
                        lambda *a, **k: Plan(steps=(PlanStep("search_statutes", {"query": "x"}),)))
    monkeypatch.setattr(ra, "execute_plan", lambda plan: [_evidence(doc_id=None)])
    monkeypatch.setattr(ra, "generate", lambda prompt: "SUFFICIENT")
    assert ra.research_angle("refund", max_rounds=1).dropped


# ------------------------------------------- interactive latency guarantee

def test_interactive_research_never_triggers_a_live_archive_scan():
    # Measured at 228s for a query that found nothing: with no court given
    # the archive scans the Supreme Court and all ~25 High Court partitions.
    # A research loop a person is waiting on must not block on that.
    from legal_ai.tools.registry import FORCED_ARGS

    assert FORCED_ARGS["search_judgments"]["live"] is False


def test_a_plan_asking_for_a_live_search_is_overridden():
    # FORCED_ARGS wins over whatever the plan asked for, so a model cannot
    # opt an interactive run into the 228s archive scan.
    from legal_ai.tools.registry import resolve_args

    assert resolve_args("search_judgments", {"query": "x", "live": True})["live"] is False


def test_resolve_args_drops_parameters_the_tool_does_not_accept():
    from legal_ai.tools.registry import resolve_args

    assert "temperature" not in resolve_args("search_statutes", {"query": "x", "temperature": 0.7})


def test_resolve_args_applies_the_search_limit_only_when_unspecified():
    from legal_ai.tools.registry import SEARCH_LIMIT, resolve_args

    assert resolve_args("search_statutes", {"query": "x"})["limit"] == SEARCH_LIMIT
    assert resolve_args("search_statutes", {"query": "x", "limit": 3})["limit"] == 3


def test_resolve_args_of_an_unregistered_tool_is_empty():
    from legal_ai.tools.registry import resolve_args

    assert resolve_args("invented_tool", {"query": "x"}) == {}


def test_get_tool_returns_none_rather_than_raising_for_an_invented_name():
    # A model inventing a tool is a step to drop, not an error to unwind the
    # whole run with.
    from legal_ai.tools.registry import get_tool

    assert get_tool("delete_everything") is None
    assert get_tool("search_statutes") is not None


def test_db_only_judgment_search_returns_quickly_and_says_why():
    from legal_ai.ingestion.judgments.dynamic_search import search_judgment

    result = search_judgment("a case that is certainly not stored anywhere", live=False)
    assert result.found is False
    assert any("live search was not attempted" in note for note in result.notes)


def test_collected_evidence_is_reranked_not_left_in_plan_order():
    # Plan order carries no relevance signal. Returning it directly measured
    # MRR 0.338 against 0.467 for plain retrieval -- the agent was throwing
    # away the ranking fusion and reranking exist to produce.
    relevant = _evidence(
        "act:2158:sec-18",
        "Return of amount and compensation. If the promoter fails to give "
        "possession the allottee may withdraw and claim a refund with interest.",
    )
    noise = _evidence("act:20062:sec-103", "Punishment for murder.")
    ranked = ra.rank_by_relevance(
        "refund when the promoter fails to give possession", [noise, relevant], limit=10
    )
    assert ranked[0].document_id == "act:2158:sec-18"


def test_ranking_respects_the_limit():
    items = [_evidence(f"act:1:sec-{i}", f"provision {i} about contracts") for i in range(20)]
    assert len(ra.rank_by_relevance("contract provision", items, limit=5)) == 5


def test_ranking_a_single_result_is_a_no_op():
    single = [_evidence()]
    assert ra.rank_by_relevance("anything", single, limit=10) == single


def test_search_steps_request_a_deeper_slice_than_the_human_default():
    # The tool default of 5 is tuned for a person reading a list; an agent
    # that reranks afterwards wants more to rerank from.
    from legal_ai.tools.registry import SEARCH_LIMIT

    assert SEARCH_LIMIT > 5


def test_a_plan_always_begins_with_the_statutory_rewrite(monkeypatch):
    # The rewrite is the largest measured gain in the project (MRR 0.467 ->
    # 0.670). Too valuable to leave to whether the planner happens to phrase
    # its first query well.
    from legal_ai.agents import planner

    monkeypatch.setattr(planner, "rewrite_query", lambda q: "promoter fails to give possession")
    monkeypatch.setattr(planner, "generate", lambda p: '[{"tool":"search_statutes","args":{"query":"other"}}]')
    plan = planner.build_plan("builder did not hand over my flat")
    assert plan.steps[0].args["query"] == "promoter fails to give possession"


def test_a_planner_query_identical_to_the_rewrite_is_not_run_twice(monkeypatch):
    from legal_ai.agents import planner

    monkeypatch.setattr(planner, "rewrite_query", lambda q: "same query")
    monkeypatch.setattr(planner, "generate", lambda p: '[{"tool":"search_statutes","args":{"query":"same query"}}]')
    assert len(planner.build_plan("q").steps) == 1


def test_the_rewrite_survives_the_planner_failing(monkeypatch):
    from legal_ai.agents import planner

    monkeypatch.setattr(planner, "rewrite_query", lambda q: "statutory phrasing")
    monkeypatch.setattr(planner, "generate", lambda p: (_ for _ in ()).throw(RuntimeError("429")))
    plan = planner.build_plan("q")
    assert len(plan.steps) == 1
    assert plan.steps[0].args["query"] == "statutory phrasing"


def test_the_rewrite_falls_back_to_the_original_question(monkeypatch):
    from legal_ai.agents import rewrite

    monkeypatch.setattr(rewrite, "generate", lambda p: (_ for _ in ()).throw(RuntimeError("429")))
    assert rewrite.rewrite_query("my builder is late") == "my builder is late"


def test_evals_measure_the_rewrite_that_actually_ships():
    # A second copy in evals/ would let the measured thing and the shipped
    # thing drift apart, which is the one failure a harness must not have.
    from evals.rewrite import rewrite_query as measured
    from legal_ai.agents.rewrite import rewrite_query as shipped

    assert measured is shipped
