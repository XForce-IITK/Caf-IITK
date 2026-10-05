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
from app.modules.ordering.schemas import OrderOut, PlaceOrderRequest
from app.modules.ordering.service import (
    MenuNotOpenError,
    OrderService,
    PriceChangedError,
    UnavailableError,
)
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
