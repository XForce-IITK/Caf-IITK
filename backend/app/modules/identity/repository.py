import uuid
from datetime import datetime

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models.enums import Role
from app.models.identity import RefreshToken, User
from app.models.platform import RateLimit


class UserRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, user_id: uuid.UUID) -> User | None:
        return self.session.get(User, user_id)

    def get_by_email(self, email: str) -> User | None:
        return self.session.scalars(select(User).where(User.email == email)).one_or_none()

    def get_for_update(self, user_id: uuid.UUID) -> User | None:
        return self.session.scalars(
            select(User).where(User.id == user_id).with_for_update()
        ).one_or_none()

    def list_staff(self) -> list[User]:
        """Kitchen Staff and Administrators, by name; Students are not listed."""
        return list(
            self.session.scalars(
                select(User).where(User.role != Role.STUDENT).order_by(User.name, User.email)
            )
        )

    def add(self, *, name: str, email: str, password_hash: str, role: Role) -> User:
        user = User(name=name, email=email, password_hash=password_hash, role=role)
        self.session.add(user)
        self.session.flush()
        return user


class RefreshTokenRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, *, user_id: uuid.UUID, token_hash: str, expires_at: datetime) -> RefreshToken:
        token = RefreshToken(user_id=user_id, token_hash=token_hash, expires_at=expires_at)
        self.session.add(token)
        self.session.flush()
        return token

    def get_by_hash_for_update(self, token_hash: str) -> RefreshToken | None:
        """Lock the row so two concurrent refreshes of one token cannot both rotate it."""
        return self.session.scalars(
            select(RefreshToken).where(RefreshToken.token_hash == token_hash).with_for_update()
        ).one_or_none()

    def revoke_all_for_user(self, user_id: uuid.UUID, now: datetime) -> None:
        self.session.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=now)
        )


class RateLimitRepository:
    """Counters in `rate_limits`, one row per subject and window (SADD: shared counters)."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def take(self, subject: str, window_start: datetime, cap: int) -> bool:
        """Count one against the window unless it already holds `cap`; return whether counted.

        A single upsert, so concurrent requests on any API worker cannot overshoot the cap.
        """
        statement = (
            insert(RateLimit)
            .values(subject=subject, window_start=window_start, count=1)
            .on_conflict_do_update(
                index_elements=[RateLimit.subject, RateLimit.window_start],
                set_={"count": RateLimit.count + 1},
                where=RateLimit.count < cap,
            )
            .returning(RateLimit.count)
        )
        return self.session.execute(statement).scalar_one_or_none() is not None

    def give_back(self, subject: str, window_start: datetime) -> None:
        self.session.execute(
            update(RateLimit)
            .where(
                RateLimit.subject == subject,
                RateLimit.window_start == window_start,
                RateLimit.count > 0,
            )
            .values(count=RateLimit.count - 1)
        )

    def delete_before(self, cutoff: datetime) -> int:
        result = self.session.execute(delete(RateLimit).where(RateLimit.window_start < cutoff))
        return result.rowcount  # type: ignore[attr-defined, no-any-return]
