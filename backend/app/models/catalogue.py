import uuid
from datetime import datetime, time

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Time,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import DiscountScope, ItemCategory, ItemStatus
from app.models.types import CreatedAt, UpdatedAt, UuidPk, pg_enum


class MenuItem(Base):
    __tablename__ = "menu_items"
    __table_args__ = (
        # FR-8: price Rs 1.00 - Rs 500.00, stored in paise
        CheckConstraint("price_paise BETWEEN 100 AND 50000", name="price_range"),
        # FR-8: name unique among ACTIVE items only
        Index(
            "uq_menu_items_active_name",
            text("lower(name)"),
            unique=True,
            postgresql_where=text("status = 'ACTIVE'"),
        ),
    )

    id: Mapped[UuidPk]
    name: Mapped[str] = mapped_column(String(60))
    description: Mapped[str] = mapped_column(String(300), default="", server_default="")
    category: Mapped[ItemCategory] = mapped_column(pg_enum(ItemCategory, "item_category"))
    price_paise: Mapped[int] = mapped_column(Integer)
    status: Mapped[ItemStatus] = mapped_column(
        pg_enum(ItemStatus, "item_status"), default=ItemStatus.ACTIVE, server_default="ACTIVE"
    )
    unavailable: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    unavailable_reason: Mapped[str | None] = mapped_column(Text)
    unavailable_source: Mapped[str | None] = mapped_column(String(20))
    unavailable_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[CreatedAt]
    updated_at: Mapped[UpdatedAt]


class DiscountRule(Base):
    __tablename__ = "discount_rules"
    __table_args__ = (
        CheckConstraint("pct BETWEEN 1 AND 50", name="pct_range"),
        CheckConstraint("start_time < end_time", name="time_order"),
    )

    id: Mapped[UuidPk]
    start_time: Mapped[time] = mapped_column(Time)
    end_time: Mapped[time] = mapped_column(Time)
    pct: Mapped[int] = mapped_column(Integer)
    scope: Mapped[DiscountScope] = mapped_column(pg_enum(DiscountScope, "discount_scope"))
    # Set only when scope = CATEGORY; ITEMS scope uses discount_rule_items.
    category: Mapped[ItemCategory | None] = mapped_column(pg_enum(ItemCategory, "item_category"))
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    created_at: Mapped[CreatedAt]


class DiscountRuleItem(Base):
    __tablename__ = "discount_rule_items"

    rule_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("discount_rules.id", ondelete="CASCADE"), primary_key=True
    )
    item_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("menu_items.id"), primary_key=True)
