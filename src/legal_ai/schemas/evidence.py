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
    """Where in the document the passage sits.

    `label` is the structural marker as the document writes it -- "(1)",
    "(a)", a proviso -- which is what a reader needs to find the passage
    again. `paragraph` is set only when that marker is a plain number, as
    judgments use.
    """

    page: Optional[int] = None
    paragraph: Optional[int] = None
    label: Optional[str] = None


class Provenance(BaseModel):
    source: SourceRef
    retrieved_at: datetime
    licence: str
    attribution_required: bool


class Evidence(BaseModel):
    """One retrieved passage with everything needed to show it to a user.

    `content` is the passage that actually matched, not the whole document.
    The Source details panel in design/UX_FLOWS.md renders court, case name,
    citation and the relevant extract, and every one of those has to travel
    with the evidence or the panel cannot be built.
    """

    content: str
    document_id: Optional[str] = None
    title: Optional[str] = None
    document_type: Optional[str] = None
    court: Optional[str] = None
    citation: Optional[str] = None
    provenance: Provenance
    location: Optional[Location] = None
