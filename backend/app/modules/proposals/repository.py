import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import ColumnElement, exists, func, or_, select, update
from sqlalchemy.orm import Session, aliased

from app.models.agent import Proposal
from app.models.capacity import DailyInventory, ServiceDay, Slot
from app.models.catalogue import MenuItem
from app.models.enums import OrderStatus, ProposalStatus, ProposalType
from app.models.ordering import Order, OrderLine
from app.models.platform import Setting


def _superseded() -> ColumnElement[bool]:
    """FR-56: a later proposal of the same type for the same target exists.

    The target is the slot for prep priority, the service date for replenishment,
    and the service date and item for item-disable.
    """
    newer = aliased(Proposal)
    return exists().where(
        newer.type == Proposal.type,
        newer.target_date == Proposal.target_date,
        newer.created_at > Proposal.created_at,
        or_(
            Proposal.type != ProposalType.PREP_PRIORITY,
            newer.target_slot_id == Proposal.target_slot_id,
        ),
        or_(
            Proposal.type != ProposalType.DISABLE,
            newer.payload["item_id"].astext == Proposal.payload["item_id"].astext,
        ),
    )


class ProposalRepository:
    """Locks follow the canonical order (NFR-4): proposals → orders →
    daily_inventory by ascending item id → slots.
    """

    def __init__(self, session: Session) -> None:
        self.session = session

    def get_setting(self, key: str) -> Any:
        return self.session.scalar(select(Setting.value).where(Setting.key == key))

    def find(self, status: ProposalStatus | None) -> list[Proposal]:
        """Newest first."""
        query = select(Proposal).order_by(Proposal.created_at.desc(), Proposal.id)
        if status is not None:
            query = query.where(Proposal.status == status)
        return list(self.session.scalars(query))

    def lock(self, proposal_id: uuid.UUID) -> Proposal | None:
        return self.session.scalars(
            select(Proposal)
            .where(Proposal.id == proposal_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        ).one_or_none()

    def is_superseded(self, proposal_id: uuid.UUID) -> bool:
        return bool(self.session.scalar(select(_superseded()).where(Proposal.id == proposal_id)))

    def expire_stale(self, now: datetime) -> list[uuid.UUID]:
        """FR-56 / UC-26: PENDING proposals past their expiry, or superseded, become EXPIRED.

        SKIP LOCKED leaves a proposal an Administrator is deciding right now to that
        decision, which re-checks expiry itself.
        """
        stale = list(
            self.session.scalars(
                select(Proposal.id)
                .where(
                    Proposal.status == ProposalStatus.PENDING,
                    (Proposal.expires_at <= now) | _superseded(),
                )
                .with_for_update(skip_locked=True)
            )
        )
        if stale:
            self.session.execute(
                update(Proposal)
                .where(Proposal.id.in_(stale))
                .values(
                    status=ProposalStatus.EXPIRED,
                    decided_at=now,
                    version=Proposal.version + 1,
                )
                .execution_options(synchronize_session=False)
            )
        return stale

    def items(self, item_ids: list[uuid.UUID]) -> dict[uuid.UUID, MenuItem]:
        rows = self.session.scalars(
            select(MenuItem)
            .where(MenuItem.id.in_(item_ids))
            .execution_options(populate_existing=True)
        )
        return {item.id: item for item in rows}

    def service_day_exists(self, service_date: date) -> bool:
        return self.session.get(ServiceDay, service_date) is not None

    def get_slot(self, slot_id: uuid.UUID) -> Slot | None:
        return self.session.get(Slot, slot_id)

    def lock_inventory(
        self, item_ids: list[uuid.UUID], service_date: date
    ) -> dict[uuid.UUID, DailyInventory]:
        """The existing rows for the items, locked in ascending item id order."""
        rows = self.session.scalars(
            select(DailyInventory)
            .where(
                DailyInventory.item_id.in_(item_ids), DailyInventory.service_date == service_date
            )
            .order_by(DailyInventory.item_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return {row.item_id: row for row in rows}

    def add_inventory(self, item_id: uuid.UUID, service_date: date, total: int) -> DailyInventory:
        row = DailyInventory(item_id=item_id, service_date=service_date, total=total, allocated=0)
        self.session.add(row)
        self.session.flush()
        return row

    def pending_item_ids(self, slot_id: uuid.UUID) -> set[uuid.UUID]:
        """Items that ACCEPTED or PREPARING orders in the slot still need prepared."""
        return set(
            self.session.scalars(
                select(func.distinct(OrderLine.item_id))
                .join(Order, Order.id == OrderLine.order_id)
                .where(
                    Order.slot_id == slot_id,
                    Order.status.in_((OrderStatus.ACCEPTED, OrderStatus.PREPARING)),
                )
            )
        )
