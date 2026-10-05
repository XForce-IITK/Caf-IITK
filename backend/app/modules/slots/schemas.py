import uuid
from datetime import date, datetime, time
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.modules.slots.domain import NotBookableReason

# FR-17: default seat capacity per slot.
MIN_CAPACITY = 1
MAX_CAPACITY = 100


class ServiceDayConfig(BaseModel):
    """FR-17. Times are IST wall-clock; the window must lie within one day."""

    model_config = ConfigDict(extra="forbid")

    window_start: time
    window_end: time
    # Omitted -> the administrator setting P-SLOT_LEN (Table 4.0-B).
    slot_len_min: Annotated[int, Field(ge=1, le=240)] | None = None
    default_capacity: Annotated[int, Field(ge=MIN_CAPACITY, le=MAX_CAPACITY)]

    @model_validator(mode="after")
    def _window_is_ordered(self) -> Self:
        if self.window_start >= self.window_end:
            raise ValueError("window_start must be before window_end")
        return self


class SlotOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    starts_at: datetime
    ends_at: datetime
    capacity: int
    booked: int


class ServiceDayOut(BaseModel):
    service_date: date
    window_start: time
    window_end: time
    slot_len_min: int
    default_capacity: int
    slots: list[SlotOut]


class SlotAvailabilityOut(BaseModel):
    id: uuid.UUID
    starts_at: datetime
    ends_at: datetime
    remaining_seats: int
    bookable: bool
    # Why the slot cannot be booked (FR-19); null when it can.
    not_bookable_reason: NotBookableReason | None


class SlotListOut(BaseModel):
    service_date: date
    slots: list[SlotAvailabilityOut]
