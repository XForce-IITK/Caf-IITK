"""Current-user injection for protected endpoints (NFR-19, SADD 2.2)."""

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.security import InvalidTokenError, decode_access_token
from app.db.session import get_session
from app.models.identity import User
from app.modules.identity.repository import UserRepository

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
