from datetime import datetime
from typing import Any

from pydantic import BaseModel


class AuditEntryOut(BaseModel):
    """One audit entry (FR-47), with any secret-looking value redacted (FR-49)."""

    id: int
    at: datetime
    # A user ID, or null for the system or the agent; the role says which.
    actor_id: str | None
    actor_role: str | None
    action: str
    entity_type: str
    entity_id: str | None
    before: dict[str, Any] | None
    after: dict[str, Any] | None
    correlation_id: str | None


class AuditPageOut(BaseModel):
    entries: list[AuditEntryOut]
    # Pass as before_id for the next (older) page; null on the last page.
    next_before_id: int | None
