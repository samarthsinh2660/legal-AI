"""Caps and model settings for the research graph.

Every limit here is enforced in code, never in a prompt. A prompt is a
request; a cap is a guarantee.

Values are lower than open_deep_research's defaults because this runs on the
Gemini free tier, where a three-way fan-out multiplies every call.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GraphConfig:
    # Parallel research agents per supervisor round.
    max_concurrent_research_units: int = 3
    # Supervisor reflect-and-go-again rounds.
    max_researcher_iterations: int = 3
    # Tool steps a single plan may contain.
    max_plan_steps: int = 8
    # Re-research passes triggered by unsupported claims.
    max_verification_passes: int = 2


DEFAULT_CONFIG = GraphConfig()
