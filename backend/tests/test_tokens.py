import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.core.config import DEFAULT_JWT_SECRET, Settings, get_settings
from app.core.security import (
    InvalidTokenError,
    create_access_token,
    decode_access_token,
    hash_refresh_token,
    new_refresh_token,
)
from app.models.enums import Role

USER_ID = uuid.uuid4()


def test_access_token_round_trips_the_user_id() -> None:
    token = create_access_token(USER_ID, Role.STUDENT)
    assert decode_access_token(token) == USER_ID


def test_expired_access_token_is_rejected() -> None:
    issued = datetime.now(UTC) - timedelta(minutes=get_settings().access_ttl_min, seconds=1)
    token = create_access_token(USER_ID, Role.STUDENT, now=issued)
    with pytest.raises(InvalidTokenError):
        decode_access_token(token)


def test_token_signed_with_another_secret_is_rejected() -> None:
    forged = jwt.encode(
        {
            "sub": str(USER_ID),
            "type": "access",
            "iat": datetime.now(UTC),
            "exp": datetime.now(UTC) + timedelta(minutes=5),
        },
        "not-the-secret-" + "y" * 32,
        algorithm="HS256",
    )
    with pytest.raises(InvalidTokenError):
        decode_access_token(forged)


@pytest.mark.parametrize(
    "claims",
    [
        {"sub": str(USER_ID), "type": "refresh"},  # wrong type
        {"sub": "not-a-uuid", "type": "access"},  # malformed subject
        {"sub": str(USER_ID)},  # missing type
    ],
)
def test_token_with_bad_claims_is_rejected(claims: dict[str, str]) -> None:
    now = datetime.now(UTC)
    token = jwt.encode(
        {**claims, "iat": now, "exp": now + timedelta(minutes=5)},
        get_settings().jwt_secret,
        algorithm="HS256",
    )
    with pytest.raises(InvalidTokenError):
        decode_access_token(token)


def test_unsigned_token_is_rejected() -> None:
    token = jwt.encode({"sub": str(USER_ID), "type": "access"}, key=None, algorithm="none")
    with pytest.raises(InvalidTokenError):
        decode_access_token(token)


def test_refresh_tokens_are_random_and_stored_hashed() -> None:
    first, second = new_refresh_token(), new_refresh_token()
    assert first != second
    assert hash_refresh_token(first) != first
    assert hash_refresh_token(first) == hash_refresh_token(first)


def test_production_refuses_a_default_or_short_jwt_secret() -> None:
    with pytest.raises(ValueError, match="CAF_JWT_SECRET"):
        Settings(env="production", jwt_secret=DEFAULT_JWT_SECRET)
    with pytest.raises(ValueError, match="CAF_JWT_SECRET"):
        Settings(env="production", jwt_secret="too-short")
    assert Settings(env="production", jwt_secret="z" * 32).is_production
