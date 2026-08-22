"""Groundedness -- is every claim supported by evidence that actually exists?

**No model.** That is the whole point: this check cannot itself hallucinate,
which makes it the one part of verification that can be trusted without
being checked in turn. It therefore runs first, before anything more
expensive or more fallible.

The failure it exists to catch is subtle. A claim whose Evidence id was lost
somewhere upstream -- dropped by compression, invented by a model -- is not
loudly wrong. It is quietly unsupported, and an answer built on it reads
exactly like one that is supported. Checking ids against the store is the
only way to tell the difference.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import psycopg


@dataclass(frozen=True)
class Claim:
    """A statement the system intends to make, and what it rests on."""

    text: str
    evidence_ids: tuple[str, ...] = ()
    paragraph: int | None = None


@dataclass(frozen=True)
class GroundednessResult:
    grounded: list[Claim] = field(default_factory=list)
    unsupported: list[tuple[Claim, str]] = field(default_factory=list)

    @property
    def all_grounded(self) -> bool:
        return not self.unsupported

    @property
    def unsupported_texts(self) -> list[str]:
        return [claim.text for claim, _reason in self.unsupported]


def check_groundedness(
    claims: list[Claim],
    conn: psycopg.Connection,
    available_ids: set[str] | None = None,
) -> GroundednessResult:
    """Split claims into grounded and unsupported.

    `available_ids` restricts support to evidence actually retrieved in this
    thread. Without it a claim could cite a real document that this run never
    saw -- true by luck rather than by research, which is not the same thing
    and must not read the same.
    """
    grounded: list[Claim] = []
    unsupported: list[tuple[Claim, str]] = []

    cited = {doc_id for claim in claims for doc_id in claim.evidence_ids}
    real: set[str] = set()
    if cited:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT document_id FROM documents WHERE document_id = ANY(%s)",
                (list(cited),),
            )
            real = {row[0] for row in cur.fetchall()}

    for claim in claims:
        if not claim.evidence_ids:
            unsupported.append((claim, "cites no evidence"))
            continue

        missing = [doc_id for doc_id in claim.evidence_ids if doc_id not in real]
        if missing:
            unsupported.append((claim, f"cites documents that do not exist: {missing}"))
            continue

        if available_ids is not None:
            unseen = [doc_id for doc_id in claim.evidence_ids if doc_id not in available_ids]
            if unseen:
                unsupported.append(
                    (claim, f"cites documents this thread never retrieved: {unseen}")
                )
                continue

        grounded.append(claim)

    return GroundednessResult(grounded=grounded, unsupported=unsupported)
