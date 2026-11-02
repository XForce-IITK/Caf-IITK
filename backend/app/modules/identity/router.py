import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.models.identity import User
from app.modules.identity.dependencies import (
    CurrentUser,
    client_ip,
    require_permission,
    too_many_requests,
)
from app.modules.identity.permissions import Permission
from app.modules.identity.rate_limit import RateLimitExceededError
from app.modules.identity.schemas import (
    AccountOut,
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    StaffCreate,
    TokenPair,
    UserOut,
)
from app.modules.identity.service import (
    EmailAlreadyRegisteredError,
    IdentityService,
    InvalidCredentialsError,
    InvalidRefreshTokenError,
)
from app.modules.identity.staff import AccountNotFoundError, OwnAccountError, StaffService

router = APIRouter(prefix="/auth", tags=["identity"])
# UC-03: Administrator-only account management, outside /auth.
admin_router = APIRouter(prefix="/admin/users", tags=["identity"])

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


@router.post(
    "/login",
    responses={
        401: {"description": "Invalid email or password"},
        429: {"description": "Too many failed logins for this account or address (NFR-21)"},
    },
)
def login(body: LoginRequest, request: Request, session: SessionDep) -> TokenPair:
    try:
        return IdentityService(session).login(body, client_ip(request))
    except InvalidCredentialsError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password") from None
    except RateLimitExceededError as exc:
        raise too_many_requests(exc) from None


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


StaffAdmin = Annotated[User, Depends(require_permission(Permission.MANAGE_STAFF))]

_ACCOUNT_RESPONSES: dict[int | str, dict[str, object]] = {
    403: {"description": "Only the Administrator manages accounts"},
    404: {"description": "No such account"},
    409: {"description": "Administrators cannot deactivate or reactivate their own account"},
}


@admin_router.get("")
def list_staff_accounts(_admin: StaffAdmin, session: SessionDep) -> list[AccountOut]:
    """UC-03: every Kitchen Staff and Administrator account, active or not, by name."""
    return [AccountOut.model_validate(user) for user in StaffService(session).list_staff()]


@admin_router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    responses={
        403: {"description": "Only the Administrator creates accounts"},
        409: {"description": "Email already registered"},
    },
)
def create_staff_account(body: StaffCreate, admin: StaffAdmin, session: SessionDep) -> AccountOut:
    """FR-2: create a Kitchen Staff or Administrator account. Students register
    themselves, so role STUDENT is refused with 422."""
    try:
        user = StaffService(session).create(admin, body)
    except EmailAlreadyRegisteredError:
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered") from None
    return AccountOut.model_validate(user)


@admin_router.post("/{user_id}/deactivate", responses=_ACCOUNT_RESPONSES)
def deactivate_account(user_id: uuid.UUID, admin: StaffAdmin, session: SessionDep) -> AccountOut:
    """FR-3: the account can no longer log in or refresh, and its access tokens are
    refused at once. Deactivating an inactive account changes nothing."""
    return _set_active(session, admin, user_id, active=False)


@admin_router.post("/{user_id}/reactivate", responses=_ACCOUNT_RESPONSES)
def reactivate_account(user_id: uuid.UUID, admin: StaffAdmin, session: SessionDep) -> AccountOut:
    """FR-3: the account can log in again; its old refresh tokens stay revoked."""
    return _set_active(session, admin, user_id, active=True)


def _set_active(session: Session, admin: User, user_id: uuid.UUID, *, active: bool) -> AccountOut:
    try:
        user = StaffService(session).set_active(admin, user_id, active=active)
    except AccountNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Account not found") from None
    except OwnAccountError:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "You cannot change your own account's status"
        ) from None
    return AccountOut.model_validate(user)
