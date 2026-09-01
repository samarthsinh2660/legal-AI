"""The chat wire contract."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class NewThreadRequest(BaseModel):
    title: Optional[str] = Field(default=None, max_length=200)
    case_id: Optional[str] = None


class RenameThreadRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)


class MessageRequest(BaseModel):
    # Same ceiling as a research question: the message is embedded in every
    # downstream prompt, and the fan-out multiplies it.
    message: str = Field(min_length=1, max_length=4000)

    # The case's own files to put in front of the Document Agent for this
    # turn. The case itself comes from the thread, not the request: a caller
    # must not reach another matter by naming its id.
    document_ids: list[str] = Field(default_factory=list, max_length=50)
    verification_level: Optional[Literal["quick", "verified"]] = None


class MessageModel(BaseModel):
    message_id: int
    role: Literal["user", "assistant"]
    content: str
    answer: Optional[dict[str, Any]] = None
    created_at: datetime


class ThreadModel(BaseModel):
    thread_id: str
    title: str
    case_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class ReplyModel(BaseModel):
    """One turn's answer.

    `route` is echoed so a client can tell an answer drawn from the thread
    from one that searched the corpus -- they carry different authority, and
    a UI that shows them identically is making a claim we did not.
    """

    text: Optional[str] = None
    answer: Optional[dict[str, Any]] = None

    # The graph halted to ask for a missing fact. A real outcome, not an
    # error: the client needs the user's next sentence, not a fixed request.
    clarification_needed: Optional[str] = None

    route: Literal["ANSWER", "RESEARCH"]
    verification_level: Optional[str] = None
