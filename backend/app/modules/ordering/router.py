import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core import clock
from app.db.session import get_session
from app.models.identity import User
from app.modules.identity.dependencies import require_permission
from app.modules.identity.permissions import Permission
from app.modules.ordering.idempotency import (
    IdempotencyKeyHeader,
    IdempotencyKeyReusedError,
    RequestInProgressError,
)
from app.modules.ordering.retry import TransientFailureError
from app.modules.ordering.schemas import (
    CancelledOrderOut,
    CancelOrderRequest,
    OrderDetailOut,
    OrderOut,
    PlaceOrderRequest,
)
from app.modules.ordering.service import (
    MenuNotOpenError,
    OrderConflictError,
    OrderService,
    PriceChangedError,
    UnavailableError,
)
from app.modules.ordering.tracking import OrderNotFoundError, OrderTrackingService
from app.modules.payments.gateway import PaymentGateway
from app.modules.payments.mockpay_gateway import get_payment_gateway
from app.modules.pricing.service import QuantityLimitError, SlotNotFoundError, UnknownItemsError

router = APIRouter(tags=["ordering"])


@router.post(
    "/orders",
    status_code=status.HTTP_201_CREATED,
    responses={
        403: {"description": "Only Students place orders"},
        404: {"description": "Slot not found"},
        409: {
            "description": "Ordering not open yet, an item or the slot is unavailable (named in "
            "the body), the price differs from the quote (fresh quote in the body), or the "
            "original request with this key is still in progress"
        },
        422: {
            "description": "Unknown item, quantity above P-MAX_QTY, or the idempotency key was "
            "already used with a different cart"
        },
        503: {"description": "Could not complete after retries; nothing was reserved"},
    },
)
def place_order(
    body: PlaceOrderRequest,
    idempotency_key: IdempotencyKeyHeader,
    user: Annotated[User, Depends(require_permission(Permission.MANAGE_OWN_ORDERS))],
    session: Annotated[Session, Depends(get_session)],
    gateway: Annotated[PaymentGateway, Depends(get_payment_gateway)],
) -> OrderOut:
    """FR-30, FR-33: reserve the portions and a seat, then take payment.

    201 with the order in ACCEPTED, or in PAYMENT_FAILED (holds returned) when the
    payment is declined or times out. A repeat with the same key returns the same order.
    """
    try:
        return OrderService(session, gateway).place(user, body, idempotency_key, clock.now())
    except SlotNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Slot not found") from None
    except UnknownItemsError as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            {"message": "Unknown items", "item_ids": [str(i) for i in exc.item_ids]},
        ) from None
    except QuantityLimitError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from None
    except IdempotencyKeyReusedError:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Idempotency key already used with a different request",
        ) from None
    except RequestInProgressError:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "The original request is still in progress"
        ) from None
    except MenuNotOpenError as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            {"message": "Ordering is not open yet", "opens_at": exc.opens_at.isoformat()},
        ) from None
    except UnavailableError as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            {
                "message": "Items or slot unavailable",
                "item_ids": [str(i) for i in exc.item_ids],
                "slot_id": str(exc.slot_id) if exc.slot_id else None,
            },
        ) from None
    except PriceChangedError as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            {"message": "Price changed", "quote": exc.quote.model_dump(mode="json")},
        ) from None
    except TransientFailureError:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Busy, try again", headers={"Retry-After": "1"}
        ) from None


@router.get(
    "/orders/{order_id}",
    responses={
        403: {"description": "Only Students track orders"},
        404: {"description": "No such order, or it belongs to another Student"},
    },
)
def get_order(
    order_id: uuid.UUID,
    user: Annotated[User, Depends(require_permission(Permission.VIEW_OWN_ORDERS))],
    session: Annotated[Session, Depends(get_session)],
) -> OrderDetailOut:
    """FR-40: the order's current status and every transition so far, oldest first.

    The client polls this every P-POLL while the order is not finished. Another
    Student's order answers 404 and is logged as a security event (FR-7).
    """
    try:
        return OrderTrackingService(session).get_for_student(user, order_id)
    except OrderNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found") from None


@router.post(
    "/orders/{order_id}/cancel",
    responses={
        403: {"description": "Only Students cancel their own orders"},
        404: {"description": "No such order, or not the caller's"},
        409: {
            "description": "The order is READY or terminal, the cut-off has passed, the "
            "version is stale (current status, version and refund in the body), or the "
            "original request with this key is still in progress"
        },
        422: {"description": "The idempotency key was already used with a different request"},
        503: {"description": "Could not complete after retries; nothing was changed"},
    },
)
def cancel_order(
    order_id: uuid.UUID,
    body: CancelOrderRequest,
    idempotency_key: IdempotencyKeyHeader,
    user: Annotated[User, Depends(require_permission(Permission.MANAGE_OWN_ORDERS))],
    session: Annotated[Session, Depends(get_session)],
    gateway: Annotated[PaymentGateway, Depends(get_payment_gateway)],
) -> CancelledOrderOut:
    """FR-37, FR-39: cancel from ACCEPTED (100 % refund, seat and portions restored) or
    PREPARING (P-LATE_REFUND_PCT refund, seat restored) before slot start - P-CUTOFF.

    `version` is the order version the Student confirmed. A repeat with the same key
    returns the same result; there is never a second refund.
    """
    try:
        return OrderService(session, gateway).cancel(
            user, order_id, body, idempotency_key, clock.now()
        )
    except OrderNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found") from None
    except IdempotencyKeyReusedError:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Idempotency key already used with a different request",
        ) from None
    except RequestInProgressError:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "The original request is still in progress"
        ) from None
    except OrderConflictError as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            {
                "message": exc.reason,
                "status": exc.status.value,
                "version": exc.version,
                "refund_paise": exc.refund_paise,
            },
        ) from None
    except TransientFailureError:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Busy, try again", headers={"Retry-After": "1"}
        ) from None
