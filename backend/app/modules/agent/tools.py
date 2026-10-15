"""The agent's tool registry (FR-51, SADD P12): the only things the LLM can call.

Read tools return the run's snapshot of one agent_* view; they take no
arguments, so the model cannot widen what it reads. Proposal tools only *stage*
a proposal: nothing is written until the run ends, and nothing takes effect
until an Administrator approves it (FR-53 - FR-57).

`dispatch` never raises. Every outcome, including an unknown tool name (FR-60)
or malformed arguments, comes back as a result the orchestrator logs and
returns to the model as data.

Argument shape is checked here; whether IDs exist and are ACTIVE, and the
P-REPL_MAX and 500-portion bounds, are checked by the output validator (FR-58)
before anything is staged.
"""

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, ValidationError

from app.models.enums import ProposalType
from app.modules.agent.forecast import Snapshot
from app.modules.agent.llm import ToolCall, ToolSpec
from app.modules.agent.validator import OutputValidator, ProposalRejectedError
from app.modules.proposals.payloads import (
    DisablePayload,
    PrepPriorityPayload,
    ReplenishLine,
    ReplenishPayload,
)

Rationale = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]


class Outcome(StrEnum):
    OK = "OK"
    REJECTED = "REJECTED"  # not in the registry: a security event (FR-60)
    INVALID = "INVALID"  # malformed or out-of-shape arguments
    DISCARDED = "DISCARDED"  # well-formed, but fails a referential or bounds check (FR-58)


@dataclass(frozen=True)
class StagedProposal:
    type: ProposalType
    target_slot_id: uuid.UUID | None
    payload: dict[str, Any]
    rationale: str
    expires_at: datetime

    @property
    def target(self) -> tuple[ProposalType, uuid.UUID | None]:
        return (self.type, self.target_slot_id)


@dataclass
class ToolResult:
    outcome: Outcome
    # Sent back to the model as the tool message: JSON, so it is data, not instructions (FR-61).
    content: str
    summary: str
    args: dict[str, Any] = field(default_factory=dict)
    staged: StagedProposal | None = None


_NO_ARGS: dict[str, object] = {"type": "object", "properties": {}, "additionalProperties": False}


class _DisableArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    item_id: uuid.UUID
    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]
    rationale: Rationale


class _PrepPriorityArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    slot_id: uuid.UUID
    item_ids: list[uuid.UUID]
    rationale: Rationale


class _ReplenishArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    lines: Annotated[list[ReplenishLine], Field(min_length=1)]
    rationale: Rationale


READ_TOOLS: dict[str, str] = {
    "get_pending_orders": "Pending portions per item per pickup slot for the service date.",
    "get_inventory_levels": "Total, allocated and available portions per item for the date.",
    "get_slot_utilisation": "Each pickup slot's start, end, capacity, booked and remaining seats.",
    "get_historical_demand": "Portions ordered per item on each of the previous 28 service dates.",
    "get_menu_config": "ACTIVE menu items: id, name, description, category, price, unavailable.",
}

TOOL_SPECS: tuple[ToolSpec, ...] = (
    *(ToolSpec(name, description, _NO_ARGS) for name, description in READ_TOOLS.items()),
    ToolSpec(
        "propose_item_disable",
        "Propose marking an item temporarily unavailable for the rest of the service date. "
        "Needs an Administrator's approval.",
        _DisableArgs.model_json_schema(),
    ),
    ToolSpec(
        "propose_prep_priority",
        "Propose the order in which the kitchen prepares items for one slot, most urgent "
        "first. Needs an Administrator's approval.",
        _PrepPriorityArgs.model_json_schema(),
    ),
    ToolSpec(
        "propose_replenishment_plan",
        "Propose extra portions to prepare for items likely to run out on the service date. "
        "Needs an Administrator's approval.",
        _ReplenishArgs.model_json_schema(),
    ),
)

REGISTERED = frozenset(spec.name for spec in TOOL_SPECS)


def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True, default=str)


def _error(outcome: Outcome, message: str, args: dict[str, Any]) -> ToolResult:
    return ToolResult(outcome, _json({"error": message}), message, args)


class ToolRegistry:
    """Dispatches the model's tool calls against one run's snapshot."""

    def __init__(self, snapshot: Snapshot, now: datetime, repl_max: int) -> None:
        self._snapshot = snapshot
        self._now = now
        self._validator = OutputValidator(snapshot, repl_max)
        self._slot_starts = {
            s["slot_id"]: datetime.fromisoformat(s["starts_at"]) for s in snapshot.slot_utilisation
        }

    def window_start(self) -> datetime | None:
        return min(self._slot_starts.values(), default=None)

    def dispatch(self, call: ToolCall) -> ToolResult:
        if call.name not in REGISTERED:
            return _error(Outcome.REJECTED, f"unknown tool {call.name!r}", {"raw": call.arguments})
        try:
            args = json.loads(call.arguments or "{}")
        except json.JSONDecodeError:
            return _error(Outcome.INVALID, "arguments are not valid JSON", {"raw": call.arguments})
        if not isinstance(args, dict):
            return _error(Outcome.INVALID, "arguments must be a JSON object", {"raw": args})
        if call.name in READ_TOOLS:
            return self._read(call.name, args)
        return self._propose(call.name, args)

    def _read(self, name: str, args: dict[str, Any]) -> ToolResult:
        if args:
            return _error(Outcome.INVALID, f"{name} takes no arguments", args)
        rows = self._snapshot.as_tool_data()[name]
        return ToolResult(Outcome.OK, _json({"data": rows}), f"{len(rows)} rows", args)

    def _propose(self, name: str, args: dict[str, Any]) -> ToolResult:
        try:
            staged = self._stage(name, args)
        except ValidationError as exc:
            fields = sorted({".".join(map(str, e["loc"])) or "arguments" for e in exc.errors()})
            return _error(Outcome.INVALID, f"invalid arguments: {', '.join(fields)}", args)
        except ValueError as exc:
            return _error(Outcome.INVALID, str(exc), args)
        try:
            slot = str(staged.target_slot_id) if staged.target_slot_id else None
            self._validator.check(staged.type, staged.payload, slot)
        except ProposalRejectedError as exc:
            return _error(Outcome.DISCARDED, f"proposal discarded: {exc}", args)
        return ToolResult(
            Outcome.OK,
            _json({"staged": staged.type.value, "status": "awaiting Administrator approval"}),
            f"staged {staged.type.value}",
            args,
            staged,
        )

    def _stage(self, name: str, args: dict[str, Any]) -> StagedProposal:
        window_start = self.window_start()
        if name == "propose_prep_priority":
            prep = _PrepPriorityArgs.model_validate(args)
            starts_at = self._slot_starts.get(str(prep.slot_id))
            if starts_at is None:
                raise ValueError("slot_id is not a slot of this service date")
            if starts_at <= self._now:
                raise ValueError("the slot has already started")
            payload: BaseModel = PrepPriorityPayload(item_ids=prep.item_ids)
            # FR-56: a prep-priority proposal expires at the start of its slot.
            return StagedProposal(
                ProposalType.PREP_PRIORITY,
                prep.slot_id,
                payload.model_dump(mode="json"),
                prep.rationale,
                starts_at,
            )
        if window_start is None:
            raise ValueError("the service date has no service window configured")
        if window_start <= self._now:
            # It would be born EXPIRED. During service, staff flag items directly (FR-11).
            raise ValueError("the service window has opened; only prep priority can be proposed")
        # FR-56: disable and replenishment proposals expire when the service window opens.
        if name == "propose_item_disable":
            disable = _DisableArgs.model_validate(args)
            payload = DisablePayload(item_id=disable.item_id, reason=disable.reason)
            return StagedProposal(
                ProposalType.DISABLE,
                None,
                payload.model_dump(mode="json"),
                disable.rationale,
                window_start,
            )
        replenish = _ReplenishArgs.model_validate(args)
        payload = ReplenishPayload(lines=replenish.lines)
        return StagedProposal(
            ProposalType.REPLENISH,
            None,
            payload.model_dump(mode="json"),
            replenish.rationale,
            window_start,
        )
