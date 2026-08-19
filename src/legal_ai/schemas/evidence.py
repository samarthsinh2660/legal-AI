# src/legal_ai/schemas/evidence.py
"""Provenance-carrying evidence, per docs/LEGAL_DATA_SOURCES.md §28."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel

SourceType = Literal["primary", "programmatic", "research"]


class SourceRef(BaseModel):
    name: str
    url: str
    document_id: Optional[str] = None
    source_type: SourceType


class Location(BaseModel):
    page: Optional[int] = None
    paragraph: Optional[int] = None


class Provenance(BaseModel):
    source: SourceRef
    retrieved_at: datetime
    licence: str
    attribution_required: bool


class Evidence(BaseModel):
    content: str
    document_id: Optional[str] = None
    title: Optional[str] = None
    document_type: Optional[str] = None
    provenance: Provenance
    location: Optional[Location] = None
