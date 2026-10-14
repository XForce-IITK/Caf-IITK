import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.models.enums import (
    AgentRunStatus,
    AgentSource,
    AgentTrigger,
    ProposalStatus,
    ProposalType,
)


class AgentRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    trigger: AgentTrigger
    status: AgentRunStatus
    source: AgentSource | None
    started_at: datetime
    finished_at: datetime | None


class ProposalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    type: ProposalType
    target_date: date
    target_slot_id: uuid.UUID | None
    payload: dict[str, Any]
    rationale: str
    source: AgentSource
    status: ProposalStatus
    expires_at: datetime


class ToolCallOut(BaseModel):
    seq: int
    tool: str
    args: dict[str, Any]
    result_summary: str | None
    latency_ms: int | None
    outcome: str


class AgentRunDetailOut(AgentRunOut):
    """FR-63: the run, its report (FR-52), its proposals and its tool-call log (FR-62)."""

    report: dict[str, Any] | None
    proposals: list[ProposalOut]
    tool_calls: list[ToolCallOut]


class RunInProgressOut(BaseModel):
    message: str
    running_run_id: uuid.UUID
