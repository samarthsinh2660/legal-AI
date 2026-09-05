"""The shapes the drafting routes return.

`warnings` and `needs_input` are lifted out of the stored structure and put
on the model deliberately. They are what the reader has to act on -- a
draft that may be the wrong instrument, or that cannot be sent until an
advocate supplies their enrolment number -- and a field buried in a JSON
blob is a field nobody reads.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class StartedDraftModel(BaseModel):
    draft_id: str
    status: str


class DraftModel(BaseModel):
    draft_id: str
    thread_id: str
    # What the model decided to draft. Empty while it is still deciding.
    document_type: str
    # running | done | failed
    status: str
    filename: str
    # Set only on a failed draft, and always set on one.
    error: str | None = None
    created_at: datetime
    finished_at: datetime | None = None
    # False while running, and on a draft that failed.
    has_file: bool = False

    # Read off the structure so the reader sees them without downloading.
    warnings: list[str] = []
    needs_input: list[str] = []

    @classmethod
    def of(cls, row: dict) -> "DraftModel":
        structure = row.get("structure") or {}
        return cls(
            draft_id=row["draft_id"],
            thread_id=row["thread_id"],
            document_type=row["document_type"],
            status=row["status"],
            filename=row["filename"],
            error=row.get("error"),
            created_at=row["created_at"],
            finished_at=row.get("finished_at"),
            has_file=bool(row.get("has_file")),
            warnings=list(structure.get("warnings") or []),
            needs_input=list(structure.get("needs_input") or []),
        )
