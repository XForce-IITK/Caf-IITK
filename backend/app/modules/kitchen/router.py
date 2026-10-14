import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core import clock
from app.db.session import get_session
from app.models.identity import User
from app.modules.identity.dependencies import require_permission
from app.modules.identity.permissions import Permission
from app.modules.kitchen.schemas import KitchenOrderOut, KitchenQueueOut, TransitionRequest
from app.modules.kitchen.service import KitchenService
from app.modules.ordering.kitchen import KitchenTransitionService, NoShowTooEarlyError
from app.modules.ordering.retry import TransientFailureError
from app.modules.ordering.state_machine import IllegalTransitionError
from app.modules.ordering.tracking import OrderNotFoundError
from app.modules.payments.gateway import PaymentGateway
from app.modules.payments.mockpay_gateway import get_payment_gateway

router = APIRouter(tags=["kitchen"])


@router.get(
    "/kitchen/queue",
    responses={403: {"description": "Only Kitchen Staff and the Administrator see the queue"}},
)
def get_kitchen_queue(
    _user: Annotated[User, Depends(require_permission(Permission.OPERATE_KITCHEN))],
    session: Annotated[Session, Depends(get_session)],
) -> KitchenQueueOut:
    """FR-42: ACCEPTED, PREPARING and READY orders of the current and next slot.

    Orders are sorted by slot start, then confirmation time. Each slot's item
    totals follow its approved prep-priority proposal (FR-54) if there is one,
    otherwise descending count. The kitchen screen polls this every P-POLL.
    """
    return KitchenService(session).queue(clock.now())


@router.post(
    "/kitchen/orders/{order_id}/transitions",
    responses={
        403: {"description": "Only Kitchen Staff and the Administrator move orders"},
        404: {"description": "No such order"},
        409: {
            "description": "Not a legal transition from the order's current state (status in "
            "the body), or a no-show before slot end + P-NOSHOW_GRACE (allowed_from in the body)"
        },
        503: {"description": "Could not complete after retries; nothing was changed"},
    },
)
def transition_kitchen_order(
    order_id: uuid.UUID,
    body: TransitionRequest,
    user: Annotated[User, Depends(require_permission(Permission.OPERATE_KITCHEN))],
    session: Annotated[Session, Depends(get_session)],
    gateway: Annotated[PaymentGateway, Depends(get_payment_gateway)],
) -> KitchenOrderOut:
    """FR-43: Start (T5), Mark Ready (T8), Mark Picked Up (T10) or Mark No-show (T11).

    Any other move is refused with 409 and changes nothing (FR-29). A no-show keeps
    the portions and is not refunded. The order version is bumped, so a Student
    acting on what they saw before gets 409.
    """
    try:
        return KitchenTransitionService(session, gateway).advance(
            user, order_id, body.action, clock.now()
        )
    except OrderNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found") from None
    except IllegalTransitionError as exc:
        current = exc.from_status.value if exc.from_status else None
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            {
                "message": f"cannot {body.action.value} an order that is {current}",
                "status": current,
            },
        ) from None
    except NoShowTooEarlyError as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            {
                "message": "too early for a no-show",
                "status": "READY",
                "allowed_from": exc.allowed_from.isoformat(),
            },
        ) from None
    except TransientFailureError:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Busy, try again", headers={"Retry-After": "1"}
        ) from None
