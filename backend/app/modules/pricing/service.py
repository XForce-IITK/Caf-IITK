"""Price quotes (FR-25): read-only; reserves no portion or seat."""

import uuid
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.models.identity import User
from app.modules.pricing.engine import CartLine, SubsidyTerms, price_cart
from app.modules.pricing.repository import PricingRepository
from app.modules.pricing.schemas import QuoteLineOut, QuoteOut, QuoteRequest

# Discount-rule times and slot times are wall-clock IST (SRS Table 4.0-B).
IST = ZoneInfo("Asia/Kolkata")


class SlotNotFoundError(Exception):
    pass


class UnknownItemsError(Exception):
    def __init__(self, item_ids: list[uuid.UUID]) -> None:
        super().__init__("unknown or removed items")
        self.item_ids = item_ids


class QuantityLimitError(Exception):
    def __init__(self, max_qty: int) -> None:
        super().__init__(f"quantity per item may not exceed {max_qty}")
        self.max_qty = max_qty


class QuoteService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repo = PricingRepository(session)

    def quote(self, student: User, request: QuoteRequest) -> QuoteOut:
        with self.session.begin():
            settings = self.repo.get_settings(
                "P-MAX_QTY", "P-SUBSIDY_AMT_PAISE", "P-SUBSIDY_CAP_PCT"
            )
            max_qty = int(settings["P-MAX_QTY"])
            if any(line.qty > max_qty for line in request.lines):
                raise QuantityLimitError(max_qty)

            slot = self.repo.get_slot(request.slot_id)
            if slot is None:
                raise SlotNotFoundError

            requested = [line.item_id for line in request.lines]
            items = self.repo.get_active_items(requested)
            missing = [item_id for item_id in requested if item_id not in items]
            if missing:
                raise UnknownItemsError(missing)

            cart = [
                CartLine(
                    item_id=line.item_id,
                    category=items[line.item_id].category,
                    unit_price_paise=items[line.item_id].price_paise,
                    qty=line.qty,
                )
                for line in request.lines
            ]
            subsidy = SubsidyTerms(
                eligible=student.subsidy_eligible,
                already_used_today=self.repo.has_subsidised_order_on(student.id, slot.service_date),
                amount_paise=int(settings["P-SUBSIDY_AMT_PAISE"]),
                cap_pct=int(settings["P-SUBSIDY_CAP_PCT"]),
            )
            breakdown = price_cart(
                cart,
                self.repo.get_active_rules(),
                slot.starts_at.astimezone(IST).time(),
                subsidy,
            )

        return QuoteOut(
            slot_id=slot.id,
            lines=[QuoteLineOut(name=items[p.item_id].name, **vars(p)) for p in breakdown.lines],
            discounted_subtotal_paise=breakdown.discounted_subtotal_paise,
            subsidy_paise=breakdown.subsidy_paise,
            rounding_adjustment_paise=breakdown.rounding_adjustment_paise,
            payable_paise=breakdown.payable_paise,
        )
