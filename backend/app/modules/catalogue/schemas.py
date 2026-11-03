import uuid
from datetime import date
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.core.text import NoNul
from app.models.enums import ItemCategory, ItemStatus
from app.modules.catalogue.domain import NotOrderableReason

# FR-8: Rs 1.00 - Rs 500.00, in paise. Mirrors the menu_items CHECK constraint.
MIN_PRICE_PAISE = 100
MAX_PRICE_PAISE = 50_000


class ItemCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60), NoNul
    ]
    description: Annotated[str, StringConstraints(strip_whitespace=True, max_length=300), NoNul] = (
        ""
    )
    category: ItemCategory
    price_paise: Annotated[int, Field(ge=MIN_PRICE_PAISE, le=MAX_PRICE_PAISE)]


class ItemUpdate(BaseModel):
    """FR-9: the fields the Administrator may edit; the name is fixed once onboarded."""

    model_config = ConfigDict(extra="forbid")

    description: (
        Annotated[str, StringConstraints(strip_whitespace=True, max_length=300), NoNul] | None
    ) = None
    category: ItemCategory | None = None
    price_paise: Annotated[int, Field(ge=MIN_PRICE_PAISE, le=MAX_PRICE_PAISE)] | None = None

    @model_validator(mode="after")
    def _at_least_one_field_and_no_nulls(self) -> "ItemUpdate":
        if not self.model_fields_set:
            raise ValueError("give at least one of description, category, price_paise")
        nulls = sorted(name for name in self.model_fields_set if getattr(self, name) is None)
        if nulls:
            raise ValueError(f"{', '.join(nulls)} cannot be null")
        return self


class FlagRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # FR-11: why the item is paused, e.g. "gas cylinder ran out".
    reason: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200), NoNul
    ]


class ItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str
    category: ItemCategory
    price_paise: int
    status: ItemStatus
    unavailable: bool
    unavailable_reason: str | None


class MenuItemOut(BaseModel):
    id: uuid.UUID
    name: str
    description: str
    category: ItemCategory
    price_paise: int
    available_portions: int
    orderable: bool
    # Why the item cannot be ordered (FR-13); null when it can.
    not_orderable_reason: NotOrderableReason | None


class MenuOut(BaseModel):
    service_date: date
    items: list[MenuItemOut]
