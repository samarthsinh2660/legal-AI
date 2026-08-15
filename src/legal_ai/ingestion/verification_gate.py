"""The Source Verification Gate — see docs/DATA_LAYER_ARCHITECTURE.md §4.

Samples a batch, checks each sampled document has real extractable text
and (where a live primary source exists) matches it. The whole batch
promotes only if the sample passes.
"""

from __future__ import annotations

import random
from typing import Callable, Optional

from pydantic import BaseModel

from legal_ai.ingestion.schema import CanonicalDocument


class VerificationResult(BaseModel):
    passed: bool
    sampled_count: int
    failed_document_ids: list[str]
    notes: list[str]


def verify_batch(
    documents: list[CanonicalDocument],
    text_check: Callable[[CanonicalDocument], bool],
    primary_source_check: Optional[Callable[[CanonicalDocument], bool]] = None,
    sample_size: int = 20,
    rng_seed: Optional[int] = None,
) -> VerificationResult:
    rng = random.Random(rng_seed)
    sample = documents if len(documents) <= sample_size else rng.sample(documents, sample_size)

    failed_ids: list[str] = []
    notes: list[str] = []

    for doc in sample:
        if not text_check(doc):
            failed_ids.append(doc.document_id)

    if primary_source_check is not None:
        for doc in sample:
            if doc.document_id in failed_ids:
                continue
            if not primary_source_check(doc):
                failed_ids.append(doc.document_id)
        if failed_ids:
            notes.append("one or more sampled documents failed the primary source check")
    else:
        notes.append(
            "no live primary-source check was available for this source — "
            "verified text-extraction only, per "
            "docs/superpowers/specs/2026-08-15-phase1-ingestion-design.md §3.3"
        )

    return VerificationResult(
        passed=len(failed_ids) == 0,
        sampled_count=len(sample),
        failed_document_ids=failed_ids,
        notes=notes,
    )
