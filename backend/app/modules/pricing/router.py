import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.exceptions import RequestValidationError
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.models.identity import User
from app.modules.identity.dependencies import require_permission
from app.modules.identity.permissions import Permission
from app.modules.pricing.rules import (
    DiscountRuleNotFoundError,
    DiscountRuleService,
    InvalidRuleError,
)
from app.modules.pricing.schemas import (
    DiscountRuleCreate,
    DiscountRuleOut,
    DiscountRuleUpdate,
    QuoteOut,
    QuoteRequest,
)
from app.modules.pricing.service import (
    QuantityLimitError,
    QuoteService,
    SlotNotFoundError,
    UnknownItemsError,
)

router = APIRouter(tags=["pricing"])

PricingAdmin = Annotated[User, Depends(require_permission(Permission.MANAGE_PRICING))]


@router.post(
    "/quotes",
    responses={
        403: {"description": "Only Students request quotes"},
        404: {"description": "Slot not found"},
        422: {"description": "Unknown or removed item, or quantity above P-MAX_QTY"},
    },
)
def create_quote(
    body: QuoteRequest,
    user: Annotated[User, Depends(require_permission(Permission.MANAGE_OWN_ORDERS))],
    session: Annotated[Session, Depends(get_session)],
) -> QuoteOut:
    """FR-25: the full FR-24 breakdown for a cart and slot. Reserves nothing."""
    try:
        return QuoteService(session).quote(user, body)
    except SlotNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Slot not found") from None
    except UnknownItemsError as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            {"message": "Unknown or removed items", "item_ids": [str(i) for i in exc.item_ids]},
        ) from None
    except QuantityLimitError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from None


def _invalid(exc: InvalidRuleError) -> RequestValidationError:
    """The same field-level 422 as a schema failure (NFR-22)."""
    return RequestValidationError(
        [{"type": "value_error", "loc": ("body", field), "msg": msg} for field, msg in exc.problems]
    )


@router.get(
    "/admin/discount-rules",
    responses={403: {"description": "Only the Administrator manages discount rules"}},
)
def list_discount_rules(
    admin: PricingAdmin, session: Annotated[Session, Depends(get_session)]
) -> list[DiscountRuleOut]:
    """FR-22: every discount rule, active or not, by start time."""
    return DiscountRuleService(session).list_rules()


@router.post(
    "/admin/discount-rules",
    status_code=status.HTTP_201_CREATED,
    responses={
        403: {"description": "Only the Administrator manages discount rules"},
        422: {
            "description": "Invalid input: percentage outside 1-50, an empty time range, "
            "a scope without its category or items, or an unknown item"
        },
    },
)
def create_discount_rule(
    body: DiscountRuleCreate, admin: PricingAdmin, session: Annotated[Session, Depends(get_session)]
) -> DiscountRuleOut:
    """FR-22 / US-17: add a time-of-day discount; it is active immediately.

    It applies to slots starting in [start_time, end_time). Rules may overlap; a
    line gets only the highest percentage among the rules that cover it (FR-24).
    """
    try:
        return DiscountRuleService(session).create(admin, body)
    except InvalidRuleError as exc:
        raise _invalid(exc) from None


@router.patch(
    "/admin/discount-rules/{rule_id}",
    responses={
        403: {"description": "Only the Administrator manages discount rules"},
        404: {"description": "No such discount rule"},
        422: {"description": "Invalid input, an unknown field, or no field to change"},
    },
)
def update_discount_rule(
    rule_id: uuid.UUID,
    body: DiscountRuleUpdate,
    admin: PricingAdmin,
    session: Annotated[Session, Depends(get_session)],
) -> DiscountRuleOut:
    """FR-22: edit a rule, or deactivate it with `active: false`.

    Orders already placed keep their price snapshots; only later quotes see the change.
    """
    try:
        return DiscountRuleService(session).update(admin, rule_id, body)
    except DiscountRuleNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Discount rule not found") from None
    except InvalidRuleError as exc:
        raise _invalid(exc) from None
