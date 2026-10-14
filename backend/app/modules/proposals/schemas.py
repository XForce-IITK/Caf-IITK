import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, StringConstraints

from app.modules.agent.schemas import ProposalOut


class ProposalDetailOut(ProposalOut):
    """A proposal with its run (whose report holds the related forecast) and its decision."""

    run_id: uuid.UUID
    created_at: datetime
    decided_at: datetime | None
    # The rejection reason, or why re-validation failed (INVALIDATED).
    decision_reason: str | None


class RejectRequest(BaseModel):
    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]


class ProposalConflictOut(BaseModel):
    """409: the proposal was not applied; `proposal.status` says why."""

    message: str
    proposal: ProposalDetailOut
