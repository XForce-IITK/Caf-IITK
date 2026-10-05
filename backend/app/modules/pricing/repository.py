import uuid
from datetime import date
from typing import Any

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from app.models.capacity import Slot
from app.models.catalogue import DiscountRule as DiscountRuleRow
from app.models.catalogue import DiscountRuleItem, MenuItem
from app.models.enums import ItemStatus, OrderStatus
from app.models.ordering import Order
from app.models.platform import Setting
from app.modules.pricing.engine import DiscountRule

# Orders in these states no longer hold the day's subsidy (FR-24 step 4).
_SUBSIDY_RELEASED = (OrderStatus.CANCELLED, OrderStatus.PAYMENT_FAILED)


class PricingRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_slot(self, slot_id: uuid.UUID) -> Slot | None:
        return self.session.get(Slot, slot_id)

    def get_active_items(self, item_ids: list[uuid.UUID]) -> dict[uuid.UUID, MenuItem]:
        rows = self.session.scalars(
            select(MenuItem).where(MenuItem.id.in_(item_ids), MenuItem.status == ItemStatus.ACTIVE)
        )
        return {item.id: item for item in rows}

    def get_active_rules(self) -> list[DiscountRule]:
        rows = self.session.scalars(select(DiscountRuleRow).where(DiscountRuleRow.active)).all()
        items_by_rule: dict[uuid.UUID, set[uuid.UUID]] = {}
        if rows:
            links = self.session.execute(
                select(DiscountRuleItem.rule_id, DiscountRuleItem.item_id).where(
                    DiscountRuleItem.rule_id.in_([r.id for r in rows])
                )
            )
            for rule_id, item_id in links:
                items_by_rule.setdefault(rule_id, set()).add(item_id)
        return [
            DiscountRule(
                rule_id=r.id,
                start_time=r.start_time,
                end_time=r.end_time,
                pct=r.pct,
                scope=r.scope,
                category=r.category,
                item_ids=frozenset(items_by_rule.get(r.id, ())),
            )
            for r in rows
        ]

    def get_settings(self, *keys: str) -> dict[str, Any]:
        rows = self.session.execute(select(Setting.key, Setting.value).where(Setting.key.in_(keys)))
        return {key: value for key, value in rows}

    def has_subsidised_order_on(self, student_id: uuid.UUID, service_date: date) -> bool:
        return bool(
            self.session.scalar(
                select(
                    exists()
                    .where(Order.slot_id == Slot.id)
                    .where(
                        Order.student_id == student_id,
                        Order.subsidy_applied,
                        Order.status.not_in(_SUBSIDY_RELEASED),
                        Slot.service_date == service_date,
                    )
                )
            )
        )
