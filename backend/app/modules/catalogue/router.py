from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.models.identity import User
from app.modules.catalogue.schemas import ItemCreate, ItemOut
from app.modules.catalogue.service import CatalogueService, DuplicateItemNameError
from app.modules.identity.dependencies import require_permission
from app.modules.identity.permissions import Permission

router = APIRouter(tags=["catalogue"])

AdminMenuUser = Annotated[User, Depends(require_permission(Permission.MANAGE_MENU))]


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
