"""Kitchen Planning Agent data: runs, their tool and LLM calls, and proposals (SADD Figure 2.6).

The agent connects as `caf_agent`, which may only INSERT into `proposals`,
`agent_tool_calls` and `agent_llm_calls` (NFR-25). Run bookkeeping (creating the
`agent_runs` row, setting its status and report) and every proposal decision are
done by the worker's or API's `caf_app` connection.
"""

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import BigInteger, Date, DateTime, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import (
    AgentRunStatus,
    AgentSource,
    AgentTrigger,
    ProposalStatus,
    ProposalType,
)
from app.models.types import CreatedAt, UuidPk, pg_enum


class AgentRun(Base):
    __tablename__ = "agent_runs"
    __table_args__ = (
        # FR-50: at most one run in progress at a time, enforced by the database.
        Index(
            "uq_agent_runs_one_active",
            text("(true)"),
            unique=True,
            postgresql_where=text("status IN ('QUEUED', 'RUNNING')"),
        ),
    )

    id: Mapped[UuidPk]
    trigger: Mapped[AgentTrigger] = mapped_column(pg_enum(AgentTrigger, "agent_trigger"))
    requested_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    status: Mapped[AgentRunStatus] = mapped_column(pg_enum(AgentRunStatus, "agent_run_status"))
    source: Mapped[AgentSource | None] = mapped_column(pg_enum(AgentSource, "agent_source"))
    # Hash of the tool data the run planned from; an unchanged hash reuses the result (FR-64).
    input_hash: Mapped[str | None] = mapped_column(Text)
    report: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    started_at: Mapped[CreatedAt]
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AgentToolCall(Base):
    __tablename__ = "agent_tool_calls"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agent_runs.id"), index=True)
    seq: Mapped[int] = mapped_column(Integer)
    tool: Mapped[str] = mapped_column(String(64))
    args: Mapped[dict[str, Any]] = mapped_column(JSONB)
    result_summary: Mapped[str | None] = mapped_column(Text)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    outcome: Mapped[str] = mapped_column(String(32))


class AgentLlmCall(Base):
    """One LLM request: model, token counts and latency, never the prompt or the key (FR-62)."""

    __tablename__ = "agent_llm_calls"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agent_runs.id"), index=True)
    model: Mapped[str] = mapped_column(String(100))
    prompt_tokens: Mapped[int | None] = mapped_column(Integer)
    completion_tokens: Mapped[int | None] = mapped_column(Integer)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    outcome: Mapped[str] = mapped_column(String(32))


class Proposal(Base):
    """A change drafted by the agent; it takes effect only on an Administrator's approval.

    `payload` follows the shape for its `type` in `app.modules.proposals.payloads`.
    DISABLE and REPLENISH target a service date; PREP_PRIORITY targets a slot.
    """

    __tablename__ = "proposals"

    id: Mapped[UuidPk]
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agent_runs.id"), index=True)
    type: Mapped[ProposalType] = mapped_column(pg_enum(ProposalType, "proposal_type"))
    target_date: Mapped[date] = mapped_column(Date)
    target_slot_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("slots.id"))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    rationale: Mapped[str] = mapped_column(Text)
    source: Mapped[AgentSource] = mapped_column(pg_enum(AgentSource, "agent_source"))
    status: Mapped[ProposalStatus] = mapped_column(
        pg_enum(ProposalStatus, "proposal_status"),
        default=ProposalStatus.PENDING,
        server_default="PENDING",
        index=True,
    )
    created_at: Mapped[CreatedAt]
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    decided_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_reason: Mapped[str | None] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
