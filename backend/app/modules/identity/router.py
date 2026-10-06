from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.modules.identity.dependencies import CurrentUser
from app.modules.identity.schemas import (
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenPair,
    UserOut,
)
from app.modules.identity.service import (
    EmailAlreadyRegisteredError,
    IdentityService,
    InvalidCredentialsError,
    InvalidRefreshTokenError,
)

router = APIRouter(prefix="/auth", tags=["identity"])

SessionDep = Annotated[Session, Depends(get_session)]


@router.post(
    "/register",
    status_code=status.HTTP_201_CREATED,
    responses={409: {"description": "Email already registered"}},
)
def register(body: RegisterRequest, session: SessionDep) -> UserOut:
    try:
        user = IdentityService(session).register_student(body)
    except EmailAlreadyRegisteredError:
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered") from None
    return UserOut.model_validate(user)


@router.post("/login", responses={401: {"description": "Invalid email or password"}})
def login(body: LoginRequest, session: SessionDep) -> TokenPair:
    try:
        return IdentityService(session).login(body)
    except InvalidCredentialsError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password") from None


@router.post("/refresh", responses={401: {"description": "Invalid refresh token"}})
def refresh(body: RefreshRequest, session: SessionDep) -> TokenPair:
    try:
        return IdentityService(session).refresh(body.refresh_token)
    except InvalidRefreshTokenError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid refresh token") from None


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(body: RefreshRequest, user: CurrentUser, session: SessionDep) -> Response:
    IdentityService(session).logout(user, body.refresh_token)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me")
def me(user: CurrentUser) -> UserOut:
    return UserOut.model_validate(user)
