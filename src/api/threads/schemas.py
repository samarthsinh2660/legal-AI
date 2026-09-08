"""The chat wire contract."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal, Optional

from pydantic import BaseModel, Field

from api.utils.fields import Text


class NewThreadRequest(BaseModel):
    title: Optional[Annotated[Text, Field(max_length=200)]] = None
    case_id: Optional[str] = None


class RenameThreadRequest(BaseModel):
    title: Annotated[Text, Field(max_length=200)]


class MessageRequest(BaseModel):
    # Same ceiling as a research question: the message is embedded in every
    # downstream prompt, and the fan-out multiplies it.
    message: Annotated[Text, Field(max_length=4000)]

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

    # The run in flight on this thread, if there is one. What a reopened
    # tab reads to decide whether to attach to a stream -- without it the
    # only signal was a question with no answer under it, which is also
    # what a run that died looks like.
    active_run: Optional[dict] = None


class StartedRunModel(BaseModel):
    """What sending a message returns.

    Not the answer. The answer takes 30-130 seconds and is produced by a
    worker, so the request hands back the id of the run that will produce it
    and the client watches `GET /runs/{run_id}/stream`. The reply itself
    arrives as that run's terminal event and is stored as a message either
    way, so a client that never watches still finds it in the thread.
    """

    run_id: str
    thread_id: str
    status: Literal["queued"]
