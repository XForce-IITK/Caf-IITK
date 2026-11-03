"""Staff accounts (UC-03; FR-2, FR-3): created, deactivated and reactivated by an
Administrator, and audited in the same transaction (FR-47).
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models.identity import User
from app.modules.audit.service import write_audit
from app.modules.identity.repository import RefreshTokenRepository, UserRepository
from app.modules.identity.schemas import StaffCreate
from app.modules.identity.service import EmailAlreadyRegisteredError


class AccountNotFoundError(Exception):
    pass


class OwnAccountError(Exception):
    """FR-3: an Administrator cannot deactivate or reactivate their own account."""


class StaffService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.users = UserRepository(session)
        self.refresh_tokens = RefreshTokenRepository(session)

    def list_staff(self) -> list[User]:
        with self.session.begin():
            return self.users.list_staff()

    def create(self, admin: User, request: StaffCreate) -> User:
        # Hash before opening the transaction so the slow KDF holds no locks.
        password_hash = hash_password(request.password)
        try:
            with self.session.begin():
                if self.users.get_by_email(request.email) is not None:
                    raise EmailAlreadyRegisteredError
                user = self.users.add(
                    name=request.name,
                    email=request.email,
                    password_hash=password_hash,
                    role=request.role,
                )
                write_audit(
                    self.session,
                    action="ACCOUNT_CREATED",
                    entity_type="user",
                    entity_id=str(user.id),
                    actor_id=str(admin.id),
                    actor_role=admin.role.value,
                    # Never the password or its hash (NFR-20).
                    after={"email": user.email, "role": user.role.value, "is_active": True},
                )
                return user
        except IntegrityError as exc:
            # A concurrent creation won the unique constraint on users.email.
            raise EmailAlreadyRegisteredError from exc

    def set_active(self, admin: User, user_id: uuid.UUID, *, active: bool) -> User:
        """FR-3. Deactivating also revokes the account's refresh tokens; its access
        tokens stop working at once, because every request re-reads the account."""
        if user_id == admin.id:
            raise OwnAccountError
        with self.session.begin():
            user = self.users.get_for_update(user_id)
            if user is None:
                raise AccountNotFoundError
            if user.is_active == active:
                return user  # Already in that state: nothing to change or audit.
            user.is_active = active
            if not active:
                self.refresh_tokens.revoke_all_for_user(user.id, datetime.now(UTC))
            write_audit(
                self.session,
                action="ACCOUNT_REACTIVATED" if active else "ACCOUNT_DEACTIVATED",
                entity_type="user",
                entity_id=str(user.id),
                actor_id=str(admin.id),
                actor_role=admin.role.value,
                before={"is_active": not active},
                after={"is_active": active},
            )
            return user
