"""One place for every knob, following open_deep_research's configuration.py.

Before this, caps and model names were spread across graph/, agents/, llm/
and retrieval/, so "how many API calls can one question make" could only be
answered by reading six files. Every value below is enforced in code, never
in a prompt: a prompt is a request, a cap is a guarantee.

Defaults are lower than open_deep_research's because this runs on the Gemini
free tier, where a three-way fan-out multiplies every call. Each field
carries the measurement or constraint that set it.
"""

from __future__ import annotations

import os
from typing import Any

from pydantic import BaseModel, Field


class Configuration(BaseModel):
    """Runtime configuration for the research graph."""

    # ---------------------------------------------------------------- models
    # Ordered strongest first. Each model carries its OWN free-tier quota, so
    # falling through on 429 multiplies the usable budget -- eight models is
    # roughly eight times the daily allowance, which is what makes fan-out
    # viable unbilled. Verified against the live API on 2026-08-21;
    # gemini-2.5-flash is listed by models.list() but 404s on call, so
    # availability must be probed rather than read from the listing.
    model_chain: tuple[str, ...] = Field(
        default=(
            "gemini-flash-latest",
            "gemini-3.7-flash",
            "gemini-3.6-flash",
            "gemini-3.5-flash",
            "gemini-3-flash-preview",
            "gemini-3.5-flash-lite",
            "gemini-3.1-flash-lite",
            "gemini-flash-lite-latest",
            # Gemma is served by the same API on a SEPARATE quota pool.
            # Measured 2026-08-24: gemini-flash-latest returned 429 while
            # gemma-4-31b-it answered on the same key in the same second.
            # Last in the chain, so nothing changes while Gemini is healthy
            # and a Google-wide Gemini outage stops being a total outage.
            "gemma-4-31b-it",
            "gemma-4-26b-a4b-it",
        )
    )

    # Case analysis leads with Gemma on measurement, not preference.
    # evals/run_contradictions.py, 2026-08-24, same 8 cases:
    #
    #     gemini-3.6-flash   recall 0.20 (1/5)   controls clean 3/3
    #     gemma-4-31b-it     recall 1.00 (5/5)   controls clean 3/3
    #
    # Gemini flash found only the conflict stated as a plain negation and
    # missed every one needing a date or an amount compared across two
    # documents. One run each on eight cases -- a strong signal, not a
    # settled number, and the Gemini models stay behind it as fallback.
    #
    # Deliberately NOT applied to research: plan_research drives retrieval,
    # which is scored by the MRR benchmark, not this one. Changing it on
    # the strength of a contradiction eval would be measuring one thing and
    # concluding about another.
    case_model_chain: tuple[str, ...] = Field(
        default=(
            "gemma-4-31b-it",
            "gemma-4-26b-a4b-it",
            "gemini-flash-latest",
            "gemini-3.6-flash",
            "gemini-3.5-flash-lite",
        )
    )

    # Transient-overload retries per model before falling through. Low on
    # purpose: with eight models behind it, moving on beats waiting.
    max_retries_per_model: int = 2

    # Output token ceilings per role, as open_deep_research does.
    #
    # These were 512 / 1024 / 1024, "sized to the job" on the assumption
    # that the budget pays only for the visible answer. It does not. Gemini
    # 3.x models spend this budget on internal reasoning first, so the cap
    # buys thinking tokens and the answer gets whatever is left.
    #
    # Measured 2026-08-24, gemini-3.6-flash, the plan prompt:
    #
    #     cap=512    65 chars returned, JSON truncated mid-string
    #     cap=2048  219 chars returned, valid JSON
    #
    # At 512 the array never closed, json.loads failed, and plan_research
    # returned its fallback -- the user's question verbatim, with no
    # rewrite. Silently. The rewrite is the component measured to beat
    # plain retrieval, so on a verbose model the whole research path
    # quietly degraded to the baseline while every test stayed green.
    #
    # This is very likely a large part of the "+/-0.15 MRR run-to-run
    # noise" blamed on model-written queries: a terse model fits the cap
    # and rewrites, a verbose one truncates and does not. That is not
    # noise, it is a bug, and it moves with which model answered.
    #
    # Extraction gets the most room: it returns six fields over a
    # 12,000-character window, and truncation there silently drops
    # parties, dates and clauses from a case.
    plan_model_max_tokens: int = 2048
    summary_model_max_tokens: int = 2048
    extraction_model_max_tokens: int = 4096

    # A document, not an answer. A s.138 notice measured ~520 words of
    # structure, and a longer instrument is the point of having the ceiling
    # separate -- drafting must not have to borrow the summary budget.
    draft_model_max_tokens: int = 8192

    # ------------------------------------------------------------ fan-out
    # Research angles the supervisor may fan out to for one question.
    # open_deep_research defaults to 5; 3 here because the free tier
    # throttles. One angle is the expected common case -- a lookup question
    # must not spawn three searches.
    max_concurrent_research_units: int = 3

    # Supervisor reflect-and-go-again rounds.
    max_researcher_iterations: int = 3

    # Rounds a single angle may take, inside one research agent.
    max_agent_rounds: int = 2

    # Tool steps one plan may contain.
    max_plan_steps: int = 8

    # Findings returned per angle after reranking.
    limit_per_angle: int = 10

    # ------------------------------------------------------- verification
    # Re-research passes triggered by unsupported claims. The loop always
    # terminates here; on exhaustion the answer ships with the gaps flagged.
    max_verification_passes: int = 2

    # How hard the reader asked us to check. "quick" runs the deterministic
    # stages only -- citation exists, was retrieved, quoted words appear in
    # the cited text. Those cost nothing and always run: cheaper means less
    # checking effort, never no integrity, and a fabricated citation
    # reaching a user in the cheap mode would be indefensible.
    #
    # "verified" adds the Verification Agent for claims that paraphrase,
    # which nothing mechanical can settle. Measured over 50 frozen claims
    # (evals/run_verification.py), 2 runs on the model chain:
    #
    #     deterministic only   exact 0.18   false alarms 0.84
    #     with the agent       exact 0.94   false alarms 0.00
    #
    # The default is "quick" because the agent still approves roughly one
    # claim in fifty that it should not, and which one varies between runs
    # (flip rate 0.06). That is a reduction in false certainty, not its
    # removal, and it is the reader's call whether to spend on it.
    verification_level: str = "quick"   # quick | verified

    # ------------------------------------------------------- phase 7 reads
    # Two behaviours are on by default because they are free and measured.
    # Everything else Phase 7 built -- conflict detection, IRAC rendering,
    # leading-authority lookup, good-law standing -- has no automatic
    # caller: it runs only when something asks for it, so it needs no
    # switch. These two change output for every question, so they get one.

    # Order key_judgments by citation count, bench as tie-breaker, instead
    # of by document_id. The alternative is alphabetical order over opaque
    # identifiers, which puts a single-judge order above the Constitution
    # Bench that settled the point. Free: one graph read, no model call.
    rank_by_authority: bool = True

    # Interleave statutes and judgments below rank 1 in retrieval results.
    # Measured 2026-08-29 on the versioned 50-question benchmark, whole
    # corpus:
    #
    #     off   MRR 0.282   recall@5 42%   recall@10 54%
    #     on    MRR 0.333   recall@5 52%   recall@10 68%
    #
    # On by default on that measurement. Turn it off to get retrieval's raw
    # relevance order, which is what the benchmark's baseline row measures.
    interleave_result_types: bool = True

    # ---------------------------------------------------------- retrieval
    # Results a search returns to an agent. The tool default of 5 suits a
    # person reading a list; an agent wants a wider net to work from.
    #
    # Narrower values were tried and appeared worse, but that comparison is
    # not trustworthy: the benchmark varies by roughly +/-0.15 MRR run to
    # run, because the query is written by a model each time. Differences
    # of that size mean nothing from a single run. Re-measure across several
    # runs before changing this.
    search_limit: int = 40

    # Judgments fetched per search. Deliberately far below search_limit:
    # a statute result is one row already in Postgres, while a judgment
    # result is a PDF or an HTML page fetched from a third party and parsed.
    # Forty of those per query would be forty outbound requests to answer
    # one question. Enough to give a reader a choice of authorities, not
    # enough to crawl.
    judgment_search_limit: int = 5

    # Findings shorter than this are handed over as they are. Summarising
    # costs a model call and can only lose detail, so it is worth paying for
    # only when the findings would not fit in front of a reader as they are.
    summarise_above_chars: int = 4000

    # Passage characters carried per Evidence -- enough for a source panel
    # extract and for a cross-encoder to score, without shipping the document.
    passage_chars: int = 2000

    @classmethod
    def from_env(cls, **overrides: Any) -> "Configuration":
        """Build from LEGAL_AI_* environment variables, then explicit
        overrides. Only fields that exist are read, so a typo in the
        environment is ignored rather than silently creating a setting."""
        values: dict[str, Any] = {}
        for name, field in cls.model_fields.items():
            raw = os.environ.get(f"LEGAL_AI_{name.upper()}")
            if raw is None:
                continue
            if field.annotation is int:
                values[name] = int(raw)
            elif field.annotation is bool:
                values[name] = raw.strip().lower() in ("1", "true", "yes", "on")
            else:
                values[name] = raw
        values.update(overrides)
        return cls(**values)


DEFAULT_CONFIG = Configuration()
