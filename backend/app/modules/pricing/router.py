from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.models.enums import Role
from app.modules.identity.dependencies import CurrentUser
from app.modules.pricing.schemas import QuoteOut, QuoteRequest
from app.modules.pricing.service import (
    QuantityLimitError,
    QuoteService,
    SlotNotFoundError,
    UnknownItemsError,
)

router = APIRouter(tags=["pricing"])


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
    user: CurrentUser,
    session: Annotated[Session, Depends(get_session)],
) -> QuoteOut:
    """FR-25: the full FR-24 breakdown for a cart and slot. Reserves nothing."""
    # Table 4.1-A: quoting is a Student action. Replace with the shared permission
    # check once CAFIITK-129 lands.
    if user.role is not Role.STUDENT:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Forbidden")
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
