"""Package-wide: importing legal_ai must make .env visible.

Lives at the root of tests/ rather than in a domain folder because it has no
domain -- it covers a side effect of importing the package itself, which
every folder below depends on and none owns.

Silently missing keys turn the agents into plain retrieval with no error
surfacing, which is why this is tested at all.
"""

import os

import legal_ai


def test_repo_env_file_is_loaded(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    legal_ai._load_env()
    assert os.environ.get("DATABASE_URL", "").startswith("postgresql://")


def test_a_real_environment_variable_is_not_overridden(monkeypatch):
    # CI, docker-compose and `GEMINI_API_KEY=... python ...` all set the
    # environment on purpose. A checked-out .env must never win over that.
    monkeypatch.setenv("DATABASE_URL", "postgresql://deliberate/override")
    legal_ai._load_env()
    assert os.environ["DATABASE_URL"] == "postgresql://deliberate/override"


def test_the_model_key_is_available_after_import():
    # The failure this guards against is not an exception -- plan_research
    # catches every error and falls back to the question verbatim. Without
    # a key the whole agent silently becomes plain retrieval, and a
    # benchmark of it looks like a bad agent rather than an absent one.
    assert os.environ.get("GEMINI_API_KEY"), "GEMINI_API_KEY missing after package import"
