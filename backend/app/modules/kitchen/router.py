from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core import clock
from app.db.session import get_session
from app.models.identity import User
from app.modules.identity.dependencies import require_permission
from app.modules.identity.permissions import Permission
from app.modules.kitchen.schemas import KitchenQueueOut
from app.modules.kitchen.service import KitchenService

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
