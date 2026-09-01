"""The cases wire contract."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class NewCaseRequest(BaseModel):
    """What `design/UX_FLOWS.md` "Creating a case" collects, and nothing more.

    `description` is not a note field: the modal labels it as seeding the
    context every agent starts from, and `session.start_session` puts it on
    the ThreadContext for that reason.
    """

    title: str = Field(min_length=1, max_length=300)
    matter_type: Optional[str] = Field(default=None, max_length=60)
    status: Optional[str] = Field(default=None, max_length=60)
    description: Optional[str] = Field(default=None, max_length=2000)
    court: Optional[str] = Field(default=None, max_length=200)
    state: Optional[str] = Field(default=None, max_length=100)
    case_number: Optional[str] = Field(default=None, max_length=100)
    parties: list[str] = Field(default_factory=list, max_length=50)


class UpdateCaseRequest(BaseModel):
    """Every field optional: a PATCH changes what it names and nothing else."""

    title: Optional[str] = Field(default=None, min_length=1, max_length=300)
    court: Optional[str] = Field(default=None, max_length=200)
    state: Optional[str] = Field(default=None, max_length=100)
    case_number: Optional[str] = Field(default=None, max_length=100)
    matter_type: Optional[str] = Field(default=None, max_length=60)
    status: Optional[str] = Field(default=None, max_length=60)
    description: Optional[str] = Field(default=None, max_length=2000)


class AttachThreadRequest(BaseModel):
    thread_id: str


class CaseModel(BaseModel):
    case_id: str
    title: str
    court: Optional[str] = None
    state: Optional[str] = None
    case_number: Optional[str] = None
    parties: list[str] = Field(default_factory=list)
    matter_type: Optional[str] = None
    status: Optional[str] = None
    description: Optional[str] = None
    created_at: datetime
    updated_at: datetime
