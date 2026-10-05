from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core import clock
from app.db.session import get_session
from app.models.identity import User
from app.modules.identity.dependencies import require_permission
from app.modules.identity.permissions import Permission
from app.modules.slots.schemas import ServiceDayConfig, ServiceDayOut, SlotListOut
from app.modules.slots.service import DayHasOrdersError, SlotLengthError, SlotService

router = APIRouter(tags=["slots"])

AdminCapacityUser = Annotated[User, Depends(require_permission(Permission.MANAGE_CAPACITY))]
SlotReader = Annotated[User, Depends(require_permission(Permission.BROWSE_MENU))]


@router.get("/slots")
def browse_slots(
    user: SlotReader,
    session: Annotated[Session, Depends(get_session)],
    service_date: Annotated[
        date | None, Query(alias="date", description="Defaults to the current service date.")
    ] = None,
) -> SlotListOut:
    """FR-19 / US-16: a service date's pickup slots with their remaining seats."""
    return SlotService(session).browse_slots(
        service_date or clock.current_service_date(), clock.now()
    )


@router.put(
    "/admin/service-days/{service_date}",
    responses={
        403: {"description": "Only the Administrator configures service windows"},
        409: {"description": "Orders already reference this day's slots"},
        422: {"description": "Invalid window, capacity, or a slot length that does not divide it"},
    },
)
def configure_service_day(
    service_date: date,
    body: ServiceDayConfig,
    admin: AdminCapacityUser,
    session: Annotated[Session, Depends(get_session)],
) -> ServiceDayOut:
    """FR-17 / US-14: configure a service date's window and generate its slots."""
    try:
        return SlotService(session).configure_day(admin, service_date, body)
    except SlotLengthError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from None
    except DayHasOrdersError:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Orders already reference this day's slots"
        ) from None
