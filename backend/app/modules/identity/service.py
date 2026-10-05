import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import (
    burn_password_check,
    create_access_token,
    hash_password,
    hash_refresh_token,
    new_refresh_token,
    verify_password,
)
from app.models.enums import Role
from app.models.identity import User
from app.modules.identity.repository import RefreshTokenRepository, UserRepository
from app.modules.identity.schemas import LoginRequest, RegisterRequest, TokenPair


class EmailAlreadyRegisteredError(Exception):
    pass


class InvalidCredentialsError(Exception):
    """Login failed. Deliberately does not say whether the email or the password was wrong."""


class InvalidRefreshTokenError(Exception):
    pass


class IdentityService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.users = UserRepository(session)
        self.refresh_tokens = RefreshTokenRepository(session)

    def register_student(self, request: RegisterRequest) -> User:
        """Self-registration always creates a Student (FR-1); other roles come from FR-2."""
        # Hash before opening the transaction so the slow KDF holds no locks.
        password_hash = hash_password(request.password)
        try:
            with self.session.begin():
                if self.users.get_by_email(request.email) is not None:
                    raise EmailAlreadyRegisteredError
                return self.users.add(
                    name=request.name,
                    email=request.email,
                    password_hash=password_hash,
                    role=Role.STUDENT,
                )
        except IntegrityError as exc:
            # A concurrent registration won the unique constraint on users.email.
            raise EmailAlreadyRegisteredError from exc

    def ensure_account(self, *, name: str, email: str, password: str, role: Role) -> bool:
        """Create the account unless the email exists; return whether it was created.

        Used by the deployment-time seed (FR-2), never by a public endpoint.
        """
        password_hash = hash_password(password)
        with self.session.begin():
            if self.users.get_by_email(email.strip().lower()) is not None:
                return False
            self.users.add(
                name=name, email=email.strip().lower(), password_hash=password_hash, role=role
            )
            return True

    def login(self, request: LoginRequest) -> TokenPair:
        """FR-4. Unknown email, wrong password and deactivated account all fail the same way."""
        with self.session.begin():
            user = self.users.get_by_email(request.email)
            if user is None:
                burn_password_check(request.password)
                raise InvalidCredentialsError
            if not verify_password(user.password_hash, request.password) or not user.is_active:
                raise InvalidCredentialsError
            return self._issue_tokens(user, datetime.now(UTC))[0]

    def refresh(self, refresh_token: str) -> TokenPair:
        """Rotate a refresh token (NFR-19): the presented one is revoked and a new pair issued.

        Presenting a token that was already rotated means it was copied, so every
        refresh token of that user is revoked (SADD T3).
        """
        now = datetime.now(UTC)
        with self.session.begin():
            token = self.refresh_tokens.get_by_hash_for_update(hash_refresh_token(refresh_token))
            if token is None:
                raise InvalidRefreshTokenError
            if token.revoked_at is not None and token.replaced_by is not None:
                self.refresh_tokens.revoke_all_for_user(token.user_id, now)
            else:
                user = self.users.get(token.user_id)
                if (
                    token.revoked_at is not None
                    or token.expires_at <= now
                    or user is None
                    or not user.is_active
                ):
                    raise InvalidRefreshTokenError
                pair, new_token_id = self._issue_tokens(user, now)
                token.revoked_at = now
                token.replaced_by = new_token_id
                return pair
        # Reuse of a rotated token: fail only after the revocation above is committed.
        raise InvalidRefreshTokenError

    def logout(self, user: User, refresh_token: str) -> None:
        """Revoke the caller's refresh token (FR-4). Unknown or foreign tokens are ignored."""
        with self.session.begin():
            token = self.refresh_tokens.get_by_hash_for_update(hash_refresh_token(refresh_token))
            if token is not None and token.user_id == user.id and token.revoked_at is None:
                token.revoked_at = datetime.now(UTC)

    def _issue_tokens(self, user: User, now: datetime) -> tuple[TokenPair, uuid.UUID]:
        """Create a token pair; also return the stored refresh token's id for rotation."""
        settings = get_settings()
        refresh_token = new_refresh_token()
        stored = self.refresh_tokens.add(
            user_id=user.id,
            token_hash=hash_refresh_token(refresh_token),
            expires_at=now + timedelta(days=settings.refresh_ttl_days),
        )
        pair = TokenPair(
            access_token=create_access_token(user.id, user.role, now=now),
            refresh_token=refresh_token,
            expires_in=settings.access_ttl_min * 60,
            role=user.role,
        )
        return pair, stored.id
