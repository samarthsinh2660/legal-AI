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
