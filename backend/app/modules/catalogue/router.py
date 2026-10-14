import uuid
from collections.abc import Callable
from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core import clock
from app.db.session import get_session
from app.models.catalogue import MenuItem
from app.models.identity import User
from app.modules.catalogue.schemas import FlagRequest, ItemCreate, ItemOut, MenuOut
from app.modules.catalogue.service import (
    CatalogueService,
    DuplicateItemNameError,
    ItemNotActiveError,
    ItemNotFoundError,
)
from app.modules.identity.dependencies import require_permission
from app.modules.identity.permissions import Permission

router = APIRouter(tags=["catalogue"])

AdminMenuUser = Annotated[User, Depends(require_permission(Permission.MANAGE_MENU))]
FlagUser = Annotated[User, Depends(require_permission(Permission.FLAG_ITEM))]
MenuReader = Annotated[User, Depends(require_permission(Permission.BROWSE_MENU))]


@router.get("/menu")
def browse_menu(
    user: MenuReader,
    session: Annotated[Session, Depends(get_session)],
    service_date: Annotated[
        date | None, Query(alias="date", description="Defaults to the current service date.")
    ] = None,
) -> MenuOut:
    """FR-13 / US-10: the menu for a service date, with what is left of each item."""
    return CatalogueService(session).browse_menu(
        service_date or clock.current_service_date(), clock.now()
    )


@router.post(
    "/admin/items",
    status_code=status.HTTP_201_CREATED,
    responses={
        403: {"description": "Only the Administrator onboards items"},
        422: {"description": "Invalid input, or an ACTIVE item already has this name"},
    },
)
def onboard_item(
    body: ItemCreate, admin: AdminMenuUser, session: Annotated[Session, Depends(get_session)]
) -> ItemOut:
    """FR-8 / US-06: add a dish; it is ACTIVE immediately."""
    try:
        item = CatalogueService(session).onboard_item(admin, body)
    except DuplicateItemNameError:
        # US-06 AC2 specifies 422 (a validation failure), not 409.
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "An active item with this name already exists"
        ) from None
    return ItemOut.model_validate(item)


_FLAG_RESPONSES: dict[int | str, dict[str, Any]] = {
    403: {"description": "Only Kitchen Staff and the Administrator flag items"},
    404: {"description": "No such menu item"},
    409: {"description": "The item is not ACTIVE"},
}


@router.post("/items/{item_id}/flag", responses=_FLAG_RESPONSES)
def flag_item(
    item_id: uuid.UUID,
    body: FlagRequest,
    staff: FlagUser,
    session: Annotated[Session, Depends(get_session)],
) -> ItemOut:
    """FR-11 / US-09: mark an item temporarily unavailable, with a reason.

    New orders for it get 409; its portions and existing orders are unchanged.
    """
    service = CatalogueService(session)
    return _flag_change(lambda: service.flag_item(staff, item_id, body.reason))


@router.delete("/items/{item_id}/flag", responses=_FLAG_RESPONSES)
def clear_item_flag(
    item_id: uuid.UUID, staff: FlagUser, session: Annotated[Session, Depends(get_session)]
) -> ItemOut:
    """FR-11 / US-09: clear the temporary-unavailable flag; the item is orderable again."""
    service = CatalogueService(session)
    return _flag_change(lambda: service.clear_flag(staff, item_id))


def _flag_change(change: Callable[[], MenuItem]) -> ItemOut:
    try:
        item = change()
    except ItemNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Menu item not found") from None
    except ItemNotActiveError:
        raise HTTPException(status.HTTP_409_CONFLICT, "Menu item is not active") from None
    return ItemOut.model_validate(item)
