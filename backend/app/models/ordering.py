import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import (
    IdempotencyState,
    ModificationStatus,
    OrderStatus,
    PaymentCause,
    PaymentKind,
    PaymentStatus,
    Role,
)
from app.models.types import CreatedAt, UpdatedAt, UuidPk, pg_enum


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (CheckConstraint("paid_paise >= 0", name="paid_non_negative"),)

    id: Mapped[UuidPk]
    student_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    slot_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("slots.id"), index=True)
    status: Mapped[OrderStatus] = mapped_column(pg_enum(OrderStatus, "order_status"), index=True)
    # Optimistic version check serialises operations on one order (NFR-5).
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    paid_paise: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    subsidy_applied: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    created_at: Mapped[CreatedAt]
    updated_at: Mapped[UpdatedAt]


class OrderLine(Base):
    __tablename__ = "order_lines"
    __table_args__ = (CheckConstraint("qty >= 1", name="qty_positive"),)

    order_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"), primary_key=True
    )
    item_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("menu_items.id"), primary_key=True)
    qty: Mapped[int] = mapped_column(Integer)


class PriceSnapshot(Base):
    """Append-only by construction: (order_id, version) is the key (FR-27)."""

    __tablename__ = "price_snapshots"

    order_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orders.id"), primary_key=True)
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    breakdown: Mapped[dict[str, Any]] = mapped_column(JSONB)
    payable_paise: Mapped[int] = mapped_column(Integer)
    priced_at: Mapped[CreatedAt]


class OrderTransition(Base):
    __tablename__ = "order_transitions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    order_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orders.id"), index=True)
    from_status: Mapped[OrderStatus | None] = mapped_column(
        "from", pg_enum(OrderStatus, "order_status")
    )
    to_status: Mapped[OrderStatus] = mapped_column("to", pg_enum(OrderStatus, "order_status"))
    actor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    actor_role: Mapped[Role | None] = mapped_column(pg_enum(Role, "user_role"))
    reason: Mapped[str | None] = mapped_column(Text)
    at: Mapped[CreatedAt]


class OrderModification(Base):
    __tablename__ = "order_modifications"

    id: Mapped[UuidPk]
    order_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orders.id"), index=True)
    status: Mapped[ModificationStatus] = mapped_column(
        pg_enum(ModificationStatus, "modification_status")
    )
    new_slot_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("slots.id"))
    new_lines: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    diff_paise: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[CreatedAt]


class Payment(Base):
    __tablename__ = "payments"
    __table_args__ = (
        CheckConstraint("amount_paise >= 0", name="amount_non_negative"),
        # A second cancellation refund is impossible at the database level (FR-39).
        Index(
            "uq_payments_cancel_refund",
            "order_id",
            unique=True,
            postgresql_where=text("kind = 'REFUND' AND cause = 'CANCEL'"),
        ),
        # A modification refund is keyed by modification_id the same way.
        Index(
            "uq_payments_modify_refund",
            "modification_id",
            unique=True,
            postgresql_where=text("kind = 'REFUND' AND cause = 'MODIFY'"),
        ),
    )

    id: Mapped[UuidPk]
    order_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orders.id"), index=True)
    modification_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("order_modifications.id"))
    kind: Mapped[PaymentKind] = mapped_column(pg_enum(PaymentKind, "payment_kind"))
    cause: Mapped[PaymentCause] = mapped_column(pg_enum(PaymentCause, "payment_cause"))
    amount_paise: Mapped[int] = mapped_column(Integer)
    status: Mapped[PaymentStatus] = mapped_column(
        pg_enum(PaymentStatus, "payment_status"),
        default=PaymentStatus.PENDING,
        server_default="PENDING",
    )
    provider_ref: Mapped[str | None] = mapped_column(String(100))
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    created_at: Mapped[CreatedAt]
    updated_at: Mapped[UpdatedAt]


class IdempotencyKey(Base):
    """(user_id, key) primary key makes concurrent duplicates collide (NFR-7)."""

    __tablename__ = "idempotency_keys"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), primary_key=True)
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    request_hash: Mapped[str] = mapped_column(Text)
    state: Mapped[IdempotencyState] = mapped_column(pg_enum(IdempotencyState, "idempotency_state"))
    response: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), index=True
    )
