"""Password hashing (NFR-20) and token primitives (NFR-19, SADD T3).

Passwords: Argon2id via argon2-cffi. Access tokens: short-lived HS256 JWTs.
Refresh tokens: opaque random strings stored only as SHA-256 hashes.
Neither passwords nor tokens are ever logged or returned beyond issue.
"""

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from app.core.config import get_settings
from app.models.enums import Role

_hasher = PasswordHasher()
_ALGORITHM = "HS256"
# Verified against when the email is unknown, so a miss costs the same as a wrong password.
_DUMMY_HASH = _hasher.hash("timing-equaliser")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def burn_password_check(password: str) -> None:
    verify_password(_DUMMY_HASH, password)


class InvalidTokenError(Exception):
    pass


def create_access_token(user_id: uuid.UUID, role: Role, *, now: datetime | None = None) -> str:
    settings = get_settings()
    issued = now or datetime.now(UTC)
    claims = {
        "sub": str(user_id),
        "role": role.value,
        "type": "access",
        "iat": issued,
        "exp": issued + timedelta(minutes=settings.access_ttl_min),
    }
    return jwt.encode(claims, settings.jwt_secret, algorithm=_ALGORITHM)


def decode_access_token(token: str) -> uuid.UUID:
    """Return the user id from a valid, unexpired access token."""
    try:
        claims = jwt.decode(
            token,
            get_settings().jwt_secret,
            algorithms=[_ALGORITHM],
            options={"require": ["sub", "exp", "iat", "type"]},
        )
        if claims["type"] != "access":
            raise InvalidTokenError
        return uuid.UUID(claims["sub"])
    except (jwt.PyJWTError, ValueError) as exc:
        raise InvalidTokenError from exc


def new_refresh_token() -> str:
    return secrets.token_urlsafe(32)


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
