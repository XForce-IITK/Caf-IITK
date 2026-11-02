"""Authentication (NFR-19) and authorisation (FR-6) dependencies for every endpoint."""

from collections.abc import Callable
from typing import Annotated, Any

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import InvalidTokenError, decode_access_token
from app.db.session import get_session
from app.models.identity import User
from app.modules.audit.service import record_security_event
from app.modules.identity.permissions import Permission, is_permitted
from app.modules.identity.rate_limit import RateLimiter, RateLimitExceededError, order_subject
from app.modules.identity.repository import UserRepository

SessionDep = Annotated[Session, Depends(get_session)]

_bearer = HTTPBearer(auto_error=False)

_UNAUTHENTICATED = HTTPException(
    status.HTTP_401_UNAUTHORIZED,
    "Not authenticated",
    headers={"WWW-Authenticate": "Bearer"},
)


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    session: Annotated[Session, Depends(get_session)],
) -> User:
    """401 for a missing, malformed, expired or forged token, or a deactivated account."""
    if credentials is None:
        raise _UNAUTHENTICATED
    try:
        user_id = decode_access_token(credentials.credentials)
    except InvalidTokenError:
        raise _UNAUTHENTICATED from None
    user = UserRepository(session).get(user_id)
    # End the read-only transaction so services can open their own with session.begin().
    session.commit()
    if user is None or not user.is_active:
        raise _UNAUTHENTICATED
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_permission(permission: Permission) -> Callable[..., User]:
    """Allow the call only if the caller's role has `permission` (FR-6, Table 4.1-A).

    The role is read from the database user loaded by get_current_user, so a role
    change applies immediately. A denial returns 403 and is written to the audit
    log as a security event; the request body is never logged.

        @router.post("/admin/items")
        def create_item(user: Annotated[User, Depends(require_permission(Permission.MANAGE_MENU))]):
    """

    def dependency(request: Request, user: CurrentUser, session: SessionDep) -> User:
        if not is_permitted(user.role, permission):
            record_security_event(
                session,
                action="PERMISSION_DENIED",
                actor_id=str(user.id),
                actor_role=user.role.value,
                details={
                    "permission": permission.value,
                    "method": request.method,
                    "path": request.url.path,
                },
            )
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Forbidden")
        return user

    return dependency


def client_ip(request: Request) -> str:
    """The caller's address. Behind nginx this relies on the server trusting the proxy's
    X-Forwarded-For (uvicorn/gunicorn `--forwarded-allow-ips`); the header is never read
    here, so a client cannot choose its own address.
    """
    return request.client.host if request.client else "unknown"


def too_many_requests(exc: RateLimitExceededError) -> HTTPException:
    return HTTPException(
        status.HTTP_429_TOO_MANY_REQUESTS,
        f"Too many attempts. Try again in {exc.retry_after_s} seconds.",
        headers={"Retry-After": str(exc.retry_after_s)},
    )


def limit_order_requests(user: CurrentUser, session: SessionDep) -> None:
    """NFR-21: at most P order create/modify/cancel requests per minute per Student.

    Every request counts, including a repeat with the same idempotency key.

        @router.post("/orders", dependencies=[Depends(limit_order_requests)])
    """
    try:
        RateLimiter(session).take([order_subject(user.id)], cap=get_settings().order_request_limit)
    except RateLimitExceededError as exc:
        raise too_many_requests(exc) from None


TOO_MANY_ORDER_REQUESTS: dict[int | str, dict[str, Any]] = {
    429: {"description": "Too many order requests this minute (NFR-21)"}
}
