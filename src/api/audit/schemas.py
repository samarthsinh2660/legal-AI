"""The audit trail's wire contract."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class AuditEventModel(BaseModel):
    event_id: int
    action: str
    resource_type: str
    resource_id: Optional[str] = None
    status: int
    at: datetime
