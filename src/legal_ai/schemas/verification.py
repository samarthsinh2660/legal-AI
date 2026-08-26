"""Claim -- a statement the system intends to make, and what it rests on.

Here rather than in `verification/` because both sides need it: the Analyst
produces claims and the verifier consumes them, and `agents/` may import
`schemas/` but not `verification/`. Keeping the type in the checker would
make every producer depend on its own checker.

Structured, never prose. A summary that ends "Sources: a, b, c" cannot be
verified -- nothing says which sentence rests on which source. One claim
carrying its own ids can be checked by lookup.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Claim:
    """A statement the system intends to make, and what it rests on.

    An empty `evidence_ids` is representable on purpose. A claim with
    nothing behind it is exactly what the verifier exists to catch, and
    refusing to construct one would hide the failure instead of reporting
    it.
    """

    text: str
    evidence_ids: tuple[str, ...] = ()
    paragraph: int | None = None
