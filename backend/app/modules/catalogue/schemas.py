import uuid
from datetime import date
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.models.enums import ItemCategory, ItemStatus
from app.modules.catalogue.domain import NotOrderableReason

# FR-8: Rs 1.00 - Rs 500.00, in paise. Mirrors the menu_items CHECK constraint.
MIN_PRICE_PAISE = 100
MAX_PRICE_PAISE = 50_000


class ItemCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60)]
    description: Annotated[str, StringConstraints(strip_whitespace=True, max_length=300)] = ""
    category: ItemCategory
    price_paise: Annotated[int, Field(ge=MIN_PRICE_PAISE, le=MAX_PRICE_PAISE)]


class ItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str
    category: ItemCategory
    price_paise: int
    status: ItemStatus
    unavailable: bool


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
