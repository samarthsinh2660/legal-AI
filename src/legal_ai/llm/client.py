"""Gemini text generation with a multi-model fallback chain.

Each model carries its own free-tier quota, so exhausting one does not
exhaust the next. Walking the chain on 429 multiplies the usable budget,
which is what makes a fan-out research stage viable without billing.

The three failure modes are not interchangeable, and treating them alike is
what burned a day's quota on 2026-08-20:

    503 UNAVAILABLE      transient overload  -> retry the SAME model
    429 RESOURCE_EXHAUSTED  rate limited     -> back off ONCE, then move on
    404 NOT_FOUND        model retired       -> move on

A 429 is two different failures wearing one code: a per-minute rate limit,
which clears in seconds, and a daily cap, which does not. Measured
2026-08-22: three concurrent calls all returned 429 while the same call
sequentially succeeded -- that is the per-minute limit, and fan-out provokes
it by construction. So a 429 gets one short backoff before the chain moves
on. Retrying it harder than that is what destroys a daily budget.

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

# Seconds to wait after a 429 before retrying the same model once. Long
# enough to clear a per-minute window, short enough that a genuine daily cap
# costs little to discover.
RATE_LIMIT_BACKOFF_SECONDS = 8


# Counts of chain-wide failures, for evals to distinguish "the system found
# nothing" from "the API was unreachable". The two look identical in a score
# and mean opposite things.
UNAVAILABLE_COUNT = 0

# Which models actually answered, and how often. A benchmark that falls
# through the chain partway is not one measurement -- the later questions
# were answered by a weaker model than the earlier ones, and the score
# blends the two. Reporting this makes that visible instead of silent.
MODEL_USAGE: dict[str, int] = {}


def reset_model_usage() -> None:
    MODEL_USAGE.clear()


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


def generate(
    prompt: str,
    chain: tuple[str, ...] = MODEL_CHAIN,
    max_output_tokens: int | None = None,
) -> str:
    """First successful response from the chain.

    `max_output_tokens` caps the reply. Sizing it to the job is the cheapest
    lever on latency and spend, and it stops a model rambling past the point
    where its answer is useful. Per-role defaults are in
    legal_ai.config.settings.

    Raises AllModelsUnavailable if every model fails.
    """
    config = {"max_output_tokens": max_output_tokens} if max_output_tokens else None
    client = _client()
    failures: dict[str, str] = {}

    for model in chain:
        for attempt in range(MAX_RETRIES_PER_MODEL):
            try:
                response = client.models.generate_content(
                    model=model, contents=prompt, config=config
                )
                MODEL_USAGE[model] = MODEL_USAGE.get(model, 0) + 1
                return (response.text or "").strip()
            except Exception as error:
                kind = _classify(error)
                failures[model] = f"{kind}: {str(error)[:120]}"
                if kind == "transient" and attempt + 1 < MAX_RETRIES_PER_MODEL:
                    time.sleep(2 * (attempt + 1))
                    continue
                if kind == "exhausted" and attempt == 0:
                    # One backoff, in case this is the per-minute limit
                    # rather than the daily cap.
                    time.sleep(RATE_LIMIT_BACKOFF_SECONDS)
                    continue
                break  # missing, capped, or out of retries -- next model

    global UNAVAILABLE_COUNT
    UNAVAILABLE_COUNT += 1
    raise AllModelsUnavailable(f"all {len(chain)} models failed: {failures}")
