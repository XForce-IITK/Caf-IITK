import uuid
from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any

from sqlalchemy import DateTime, Enum, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import mapped_column

UuidPk = Annotated[
    uuid.UUID,
    mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")),
]
CreatedAt = Annotated[
    datetime, mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
]
UpdatedAt = Annotated[
    datetime,
    mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    ),
]
Json = Annotated[dict[str, Any], mapped_column(JSONB)]


def pg_enum(enum_cls: type[StrEnum], name: str) -> Enum:
    """A native PostgreSQL enum that stores the member values."""
    return Enum(enum_cls, name=name, values_callable=lambda e: [m.value for m in e])
