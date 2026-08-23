"""Deterministic gate between a tool result and the state.

No model. That is the point: this cannot itself hallucinate, so it is the
one check in the pipeline that can be trusted without being checked.

End-of-pipeline verification cannot do this job. By the time an answer is
assembled, an Evidence that lost its id or its provenance is simply absent,
and a groundedness check then fails **open** -- passing because there is
nothing left to check. Catching it at the boundary is the difference between
a caught error and a silent one.
"""

from __future__ import annotations

from dataclasses import dataclass

import psycopg

from legal_ai.schemas.evidence import Evidence


@dataclass(frozen=True)
class ValidationResult:
    kept: list[Evidence]
    dropped: list[tuple[str, str]]  # (document_id or "<none>", reason)

    @property
    def all_dropped(self) -> bool:
        """True when a step produced results and none survived -- the agent
        should be told, so its next round can plan around the failure."""
        return bool(self.dropped) and not self.kept


def validate(
    evidence: list[Evidence], conn: psycopg.Connection | None = None
) -> ValidationResult:
    """Keep only evidence fit to enter state.

    `conn` enables the existence check. Without it, structural checks still
    run -- useful in tests and wherever a connection is not to hand.
    """
    kept: list[Evidence] = []
    dropped: list[tuple[str, str]] = []

    structurally_ok: list[Evidence] = []
    for item in evidence:
        label = item.document_id or "<none>"
        if not item.document_id:
            dropped.append((label, "no document_id"))
        elif not item.content or not item.content.strip():
            dropped.append((label, "empty content"))
        elif item.provenance is None or not item.provenance.source.url:
            dropped.append((label, "no provenance url"))
        else:
            structurally_ok.append(item)

    if conn is None or not structurally_ok:
        return ValidationResult(kept=structurally_ok, dropped=dropped)

    ids = [item.document_id for item in structurally_ok]
    with conn.cursor() as cur:
        cur.execute("SELECT document_id FROM documents WHERE document_id = ANY(%s)", (ids,))
        real = {row[0] for row in cur.fetchall()}

    for item in structurally_ok:
        if item.document_id in real:
            kept.append(item)
        else:
            dropped.append((item.document_id, "document_id does not resolve"))

    return ValidationResult(kept=kept, dropped=dropped)


def evidence_ids_survived(summary: str, evidence: list[Evidence]) -> bool:
    """Every validated document id still appears in a compressed summary.

    The highest-risk failure in the phase: compression that drops Evidence
    ids makes every downstream claim ungroundable. Checked rather than
    trusted.
    """
    return all(item.document_id in summary for item in evidence if item.document_id)
