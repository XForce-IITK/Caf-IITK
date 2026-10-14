"""The `proposals.payload` shape for each proposal type (FR-53 - FR-55).

This is the contract between the agent run, which writes proposals (CAFIITK-164),
and the proposal decisions and kitchen queue, which read them (CAFIITK-165,
CAFIITK-158). The proposal row itself carries the target: `target_date` for every
type, plus `target_slot_id` for PREP_PRIORITY.

These models check shape only. Referential checks (items exist and are ACTIVE)
and the P-REPL_MAX bound need the database and live in the output validator
(FR-58) and in re-validation at approval (FR-57).
"""

import uuid
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, TypeAdapter, field_validator

from app.models.enums import ProposalType

# FR-55: at least one additional portion per line. The upper bound is P-REPL_MAX,
# an administrator setting, so it is checked against the database, not here.
MIN_ADDITIONAL_PORTIONS = 1


def _distinct(item_ids: list[uuid.UUID]) -> list[uuid.UUID]:
    if len(set(item_ids)) != len(item_ids):
        raise ValueError("item IDs must be distinct")
    return item_ids


class DisablePayload(BaseModel):
    """FR-53: set the item's temporarily-unavailable flag until the end of target_date."""

    model_config = ConfigDict(extra="forbid")

    item_id: uuid.UUID
    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]


class PrepPriorityPayload(BaseModel):
    """FR-54: the kitchen's prep order for target_slot_id, highest priority first."""

    model_config = ConfigDict(extra="forbid")

    item_ids: Annotated[list[uuid.UUID], Field(min_length=1)]

    _check_distinct = field_validator("item_ids")(_distinct)


class ReplenishLine(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_id: uuid.UUID
    additional_portions: Annotated[int, Field(ge=MIN_ADDITIONAL_PORTIONS)]


class ReplenishPayload(BaseModel):
    """FR-55: portions to add to each item's inventory for target_date."""

    model_config = ConfigDict(extra="forbid")

    lines: Annotated[list[ReplenishLine], Field(min_length=1)]

    @field_validator("lines")
    @classmethod
    def _items_distinct(cls, lines: list[ReplenishLine]) -> list[ReplenishLine]:
        _distinct([line.item_id for line in lines])
        return lines


ProposalPayload = DisablePayload | PrepPriorityPayload | ReplenishPayload

PAYLOAD_MODELS: dict[ProposalType, type[ProposalPayload]] = {
    ProposalType.DISABLE: DisablePayload,
    ProposalType.PREP_PRIORITY: PrepPriorityPayload,
    ProposalType.REPLENISH: ReplenishPayload,
}


def parse_payload(proposal_type: ProposalType, payload: object) -> ProposalPayload:
    """Validate a stored or drafted payload against its type's shape (raises ValidationError)."""
    model: TypeAdapter[ProposalPayload] = TypeAdapter(PAYLOAD_MODELS[proposal_type])
    return model.validate_python(payload)
