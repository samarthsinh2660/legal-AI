# src/legal_ai/ingestion/schema.py
"""Canonical document schema shared by every ingestion source.

See docs/superpowers/specs/2026-08-15-phase1-ingestion-design.md §3.2.
"""

from __future__ import annotations

import hashlib
from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel

from legal_ai.schemas.evidence import Provenance

DocumentType = Literal["act", "section", "judgment"]


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class CanonicalDocument(BaseModel):
    document_id: str
    document_type: DocumentType
    title: str
    court: Optional[str] = None
    citation: Optional[str] = None
    case_number: Optional[str] = None
    parties: Optional[dict] = None
    decision_date: Optional[date] = None
    enactment_date: Optional[date] = None
    disposal_nature: Optional[str] = None
    act_id: Optional[str] = None
    full_text: str
    content_hash: str
    provenance: Provenance
    ingested_at: datetime
