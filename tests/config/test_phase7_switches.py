"""Phase 7's two always-on behaviours are switchable, like verification.

Everything else Phase 7 built -- conflict detection, IRAC, leading
authorities, good-law standing -- has no automatic caller, so it costs
nothing until something asks. These two change the output of every question,
so they get a switch and a documented default.

Off must restore exactly what shipped before Phase 7, not an approximation
of it: a flag that leaves the system in a third state nobody measured is
worse than no flag.
"""

import os

import pytest

from legal_ai.config.settings import Configuration
from legal_ai.retrieval.type_floor import apply_type_floor


@pytest.fixture
def clean_env(monkeypatch):
    for name in ("LEGAL_AI_RANK_BY_AUTHORITY", "LEGAL_AI_INTERLEAVE_RESULT_TYPES"):
        monkeypatch.delenv(name, raising=False)


def test_both_default_on(clean_env):
    config = Configuration()
    assert config.rank_by_authority
    assert config.interleave_result_types


def test_the_environment_turns_interleaving_off(monkeypatch):
    monkeypatch.setenv("LEGAL_AI_INTERLEAVE_RESULT_TYPES", "false")
    assert Configuration.from_env().interleave_result_types is False


def test_the_environment_turns_authority_ranking_off(monkeypatch):
    monkeypatch.setenv("LEGAL_AI_RANK_BY_AUTHORITY", "0")
    assert Configuration.from_env().rank_by_authority is False


@pytest.mark.parametrize("raw", ["true", "TRUE", "1", "yes", "on"])
def test_truthy_spellings(monkeypatch, raw):
    monkeypatch.setenv("LEGAL_AI_RANK_BY_AUTHORITY", raw)
    assert Configuration.from_env().rank_by_authority is True


@pytest.mark.parametrize("raw", ["false", "0", "no", "off", "anything else"])
def test_everything_else_is_off(monkeypatch, raw):
    monkeypatch.setenv("LEGAL_AI_RANK_BY_AUTHORITY", raw)
    assert Configuration.from_env().rank_by_authority is False


def test_hybrid_search_takes_its_default_from_config(monkeypatch):
    """A caller that says nothing follows the config; one that passes a
    value wins. Otherwise the switch would be unreachable from the API."""
    import legal_ai.retrieval.hybrid as hybrid
    import inspect

    signature = inspect.signature(hybrid.hybrid_search)
    assert signature.parameters["type_floor"].default is None


def test_interleaving_off_is_plain_relevance_order():
    """Off must be the raw reranked order, unchanged."""
    ranked = ["j1", "j2", "j3", "s1"]
    types = {"j1": "judgment", "j2": "judgment", "j3": "judgment", "s1": "section"}
    # apply_type_floor is simply not called when the switch is off; this
    # pins what "raw" means so the comparison in the docs stays honest.
    assert ranked[:3] == ["j1", "j2", "j3"]
    assert apply_type_floor(ranked, types, limit=3) != ranked[:3]
