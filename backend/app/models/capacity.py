"""Per-date capacity: service days, pickup slots and prepared portions.

`slots.booked` and `daily_inventory.allocated` are counters guarded by CHECK
constraints, so even buggy application code cannot oversell (NFR-2, ADR-06).
"""

import uuid
from datetime import date, datetime, time

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Integer, Time, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.types import UuidPk


class ServiceDay(Base):
    __tablename__ = "service_days"
    __table_args__ = (
        CheckConstraint("window_start < window_end", name="window_order"),
        CheckConstraint("slot_len_min > 0", name="slot_len_positive"),
        CheckConstraint("default_capacity BETWEEN 1 AND 100", name="capacity_range"),
    )

    service_date: Mapped[date] = mapped_column(Date, primary_key=True)
    window_start: Mapped[time] = mapped_column(Time)
    window_end: Mapped[time] = mapped_column(Time)
    slot_len_min: Mapped[int] = mapped_column(Integer)
    default_capacity: Mapped[int] = mapped_column(Integer)


class Slot(Base):
    __tablename__ = "slots"
    __table_args__ = (
        CheckConstraint("0 <= booked AND booked <= capacity", name="booked_within_capacity"),
        CheckConstraint("starts_at < ends_at", name="time_order"),
        UniqueConstraint("service_date", "starts_at", name="uq_slots_service_date_starts_at"),
    )

    id: Mapped[UuidPk]
    service_date: Mapped[date] = mapped_column(
        ForeignKey("service_days.service_date", ondelete="CASCADE"), index=True
    )
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    capacity: Mapped[int] = mapped_column(Integer)
    booked: Mapped[int] = mapped_column(Integer, default=0, server_default="0")


class DailyInventory(Base):
    __tablename__ = "daily_inventory"
    __table_args__ = (
        CheckConstraint("total BETWEEN 0 AND 500", name="total_range"),
        CheckConstraint("0 <= allocated AND allocated <= total", name="allocated_within_total"),
    )

    item_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("menu_items.id"), primary_key=True)
    service_date: Mapped[date] = mapped_column(
        ForeignKey("service_days.service_date"), primary_key=True
    )
    total: Mapped[int] = mapped_column(Integer)
    allocated: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
