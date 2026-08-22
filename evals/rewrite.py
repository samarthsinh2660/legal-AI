"""Re-export of the production rewrite, so evals measure what ships.

The implementation lives in legal_ai.agents.rewrite. Keeping a second copy
here would let the measured thing and the shipped thing drift apart, which
is the one failure a harness must not have.
"""

from legal_ai.agents.rewrite import PROMPT, rewrite_query

__all__ = ["rewrite_query", "PROMPT"]
