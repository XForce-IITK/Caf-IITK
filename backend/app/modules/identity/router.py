from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.modules.identity.schemas import RegisterRequest, UserOut
from app.modules.identity.service import EmailAlreadyRegisteredError, IdentityService

router = APIRouter(prefix="/auth", tags=["identity"])


@router.post(
    "/register",
    status_code=status.HTTP_201_CREATED,
    responses={409: {"description": "Email already registered"}},
)
def register(body: RegisterRequest, session: Annotated[Session, Depends(get_session)]) -> UserOut:
    try:
        user = IdentityService(session).register_student(body)
    except EmailAlreadyRegisteredError:
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered") from None
    return UserOut.model_validate(user)
