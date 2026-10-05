import uuid
from datetime import date
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

# FR-14: 0-500 prepared portions. Mirrors the daily_inventory total_range CHECK.
MAX_PORTIONS = 500


class InventorySet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total: Annotated[int, Field(ge=0, le=MAX_PORTIONS)]


class InventoryOut(BaseModel):
    item_id: uuid.UUID
    service_date: date
    total: int
    allocated: int
    available: int
