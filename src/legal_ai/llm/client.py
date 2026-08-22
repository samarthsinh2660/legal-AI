"""Gemini text generation with a multi-model fallback chain.

Each model carries its own free-tier quota, so exhausting one does not
exhaust the next. Walking the chain on 429 multiplies the usable budget,
which is what makes a fan-out research stage viable without billing.

The three failure modes are not interchangeable, and treating them alike is
what burned a day's quota on 2026-08-20:

    503 UNAVAILABLE      transient overload  -> retry the SAME model
    429 RESOURCE_EXHAUSTED  daily cap        -> move on, NEVER retry
    404 NOT_FOUND        model retired       -> move on

Model chain verified against the live API on 2026-08-21. `gemini-2.5-flash`
and `gemini-2.5-flash-lite` are listed by models.list() but return 404 on
call, so availability must be probed rather than read from the listing.
"""

from __future__ import annotations

import os
import time

from legal_ai.config import DEFAULT_CONFIG

# Re-exported for callers that want the chain without importing config.
# The values live in legal_ai.config.settings, which carries the reasoning.
MODEL_CHAIN: tuple[str, ...] = DEFAULT_CONFIG.model_chain
MAX_RETRIES_PER_MODEL = DEFAULT_CONFIG.max_retries_per_model


# Counts of chain-wide failures, for evals to distinguish "the system found
# nothing" from "the API was unreachable". The two look identical in a score
# and mean opposite things.
UNAVAILABLE_COUNT = 0


def reset_unavailable_count() -> None:
    global UNAVAILABLE_COUNT
    UNAVAILABLE_COUNT = 0


class AllModelsUnavailable(RuntimeError):
    """Every model in the chain failed. Carries the last error per model so
    a quota problem is distinguishable from a genuine outage."""


def _client():
    from google import genai

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not set")
    return genai.Client(api_key=api_key)


def _classify(error: Exception) -> str:
    text = str(error)
    if "429" in text or "RESOURCE_EXHAUSTED" in text:
        return "exhausted"
    if "404" in text or "NOT_FOUND" in text:
        return "missing"
    if "503" in text or "UNAVAILABLE" in text:
        return "transient"
    return "other"


def generate(prompt: str, chain: tuple[str, ...] = MODEL_CHAIN) -> str:
    """First successful response from the chain.

    Raises AllModelsUnavailable if every model fails.
    """
    client = _client()
    failures: dict[str, str] = {}

    for model in chain:
        for attempt in range(MAX_RETRIES_PER_MODEL):
            try:
                response = client.models.generate_content(model=model, contents=prompt)
                return (response.text or "").strip()
            except Exception as error:
                kind = _classify(error)
                failures[model] = f"{kind}: {str(error)[:120]}"
                if kind == "transient" and attempt + 1 < MAX_RETRIES_PER_MODEL:
                    time.sleep(2 * (attempt + 1))
                    continue
                break  # exhausted, missing, or out of retries -- next model

    global UNAVAILABLE_COUNT
    UNAVAILABLE_COUNT += 1
    raise AllModelsUnavailable(f"all {len(chain)} models failed: {failures}")
