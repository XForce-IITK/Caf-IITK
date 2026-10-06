import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.models.identity import User
from app.modules.identity.dependencies import require_permission
from app.modules.identity.permissions import Permission
from app.modules.inventory.schemas import InventoryOut, InventorySet
from app.modules.inventory.service import (
    BelowAllocatedError,
    InventoryService,
    ItemNotActiveError,
    ItemNotFoundError,
    ServiceDayNotConfiguredError,
)

router = APIRouter(tags=["inventory"])

AdminCapacityUser = Annotated[User, Depends(require_permission(Permission.MANAGE_CAPACITY))]


@router.put(
    "/admin/inventory/{service_date}/{item_id}",
    responses={
        403: {"description": "Only the Administrator manages inventory"},
        404: {"description": "No such menu item"},
        409: {
            "description": "Item is not ACTIVE, the service date is not configured, "
            "or the total is below the portions already allocated"
        },
    },
)
def set_inventory(
    service_date: date,
    item_id: uuid.UUID,
    body: InventorySet,
    admin: AdminCapacityUser,
    session: Annotated[Session, Depends(get_session)],
) -> InventoryOut:
    """FR-14 / US-11: set the prepared portions of an item for a service date (0-500)."""
    try:
        row = InventoryService(session).set_total(admin, item_id, service_date, body.total)
    except ItemNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Menu item not found") from None
    except ItemNotActiveError:
        raise HTTPException(status.HTTP_409_CONFLICT, "Menu item is not active") from None
    except ServiceDayNotConfiguredError:
        raise HTTPException(status.HTTP_409_CONFLICT, "Service date is not configured") from None
    except BelowAllocatedError as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Total cannot be below the {exc.allocated} portions already allocated",
        ) from None
    return InventoryOut(
        item_id=row.item_id,
        service_date=row.service_date,
        total=row.total,
        allocated=row.allocated,
        available=row.total - row.allocated,
    )
