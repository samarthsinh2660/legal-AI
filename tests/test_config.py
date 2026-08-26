"""Configuration is answerable from one file, and caps live in code.

Before consolidation these values were spread across graph/, agents/, llm/,
tools/ and retrieval/, so "how many API calls can one question make" could
only be answered by reading six files.
"""

import os

from legal_ai.config import DEFAULT_CONFIG, Configuration


def test_the_model_chain_has_real_fallbacks():
    # Each model carries its own free-tier quota, so the chain length is
    # roughly the multiplier on the daily budget.
    assert len(DEFAULT_CONFIG.model_chain) >= 5
    assert "gemini-2.5-flash" not in DEFAULT_CONFIG.model_chain


def test_caps_are_bounded_and_conservative():
    assert DEFAULT_CONFIG.max_concurrent_research_units == 3
    assert DEFAULT_CONFIG.max_plan_steps == 8
    assert DEFAULT_CONFIG.max_verification_passes == 2
    assert DEFAULT_CONFIG.max_agent_rounds == 2


def test_every_consumer_reads_the_same_values():
    from legal_ai.llm.client import MODEL_CHAIN
    from legal_ai.retrieval.evidence_builder import PASSAGE_CHARS
    from legal_ai.tools.registry import SEARCH_LIMIT

    assert MODEL_CHAIN == DEFAULT_CONFIG.model_chain
    assert SEARCH_LIMIT == DEFAULT_CONFIG.search_limit
    assert PASSAGE_CHARS == DEFAULT_CONFIG.passage_chars


def test_an_integer_setting_can_be_overridden_from_the_environment(monkeypatch):
    monkeypatch.setenv("LEGAL_AI_MAX_PLAN_STEPS", "4")
    assert Configuration.from_env().max_plan_steps == 4


def test_an_unknown_environment_variable_is_ignored(monkeypatch):
    # A typo must not silently create a setting nothing reads.
    monkeypatch.setenv("LEGAL_AI_NOT_A_REAL_SETTING", "9")
    config = Configuration.from_env()
    assert not hasattr(config, "not_a_real_setting")


def test_explicit_overrides_beat_the_environment(monkeypatch):
    monkeypatch.setenv("LEGAL_AI_MAX_PLAN_STEPS", "4")
    assert Configuration.from_env(max_plan_steps=6).max_plan_steps == 6


def test_graph_config_is_the_same_object_so_old_imports_still_work():
    from legal_ai.graph.configuration import GraphConfig

    assert GraphConfig is Configuration


def test_gemma_is_in_the_default_chain_as_a_fallback():
    # Served by the same API on a separate quota pool. Measured
    # 2026-08-24: gemini-flash-latest returned 429 while gemma-4-31b-it
    # answered on the same key in the same second, so a Gemini-wide outage
    # stops being a total outage.
    from legal_ai.config import DEFAULT_CONFIG

    assert any("gemma" in model for model in DEFAULT_CONFIG.model_chain)


def test_gemma_is_last_so_nothing_changes_while_gemini_is_healthy():
    from legal_ai.config import DEFAULT_CONFIG

    first_gemma = next(
        i for i, m in enumerate(DEFAULT_CONFIG.model_chain) if "gemma" in m
    )
    assert all("gemma" in m for m in DEFAULT_CONFIG.model_chain[first_gemma:])


def test_case_analysis_leads_with_gemma():
    # On measurement, not preference: recall 1.00 vs 0.20 for gemini flash
    # on evals/run_contradictions.py. Gemini stays behind it as fallback.
    from legal_ai.config import DEFAULT_CONFIG

    assert DEFAULT_CONFIG.case_model_chain[0].startswith("gemma")
    assert any("gemini" in m for m in DEFAULT_CONFIG.case_model_chain)


def test_research_is_not_switched_on_a_contradiction_result():
    # plan_research drives retrieval, which the MRR benchmark scores --
    # not the contradiction eval. Changing it here would be measuring one
    # thing and concluding about another.
    from legal_ai.config import DEFAULT_CONFIG

    assert DEFAULT_CONFIG.model_chain[0].startswith("gemini")


def test_token_caps_leave_room_for_reasoning_tokens():
    # Gemini 3.x spends max_output_tokens on internal reasoning before it
    # writes anything. Measured 2026-08-24 on gemini-3.6-flash: a cap of
    # 512 returned 65 characters and truncated the plan JSON mid-string,
    # so json.loads failed and plan_research silently returned the user's
    # question unrewritten. A cap that small is not a limit, it is an
    # off switch for the component that beats plain retrieval.
    from legal_ai.config import DEFAULT_CONFIG

    assert DEFAULT_CONFIG.plan_model_max_tokens >= 2048
    assert DEFAULT_CONFIG.summary_model_max_tokens >= 2048


def test_extraction_has_the_largest_budget():
    # It returns six fields over a 12,000-character window; truncation
    # there drops parties, dates and clauses from a case without saying so.
    from legal_ai.config import DEFAULT_CONFIG

    assert DEFAULT_CONFIG.extraction_model_max_tokens >= DEFAULT_CONFIG.plan_model_max_tokens
