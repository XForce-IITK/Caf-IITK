from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models.enums import Role
from app.models.identity import User
from app.modules.identity.repository import UserRepository
from app.modules.identity.schemas import RegisterRequest


class EmailAlreadyRegisteredError(Exception):
    pass


class IdentityService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.users = UserRepository(session)

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
