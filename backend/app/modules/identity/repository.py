from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import Role
from app.models.identity import User


class UserRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_email(self, email: str) -> User | None:
        return self.session.scalars(select(User).where(User.email == email)).one_or_none()

    def add(self, *, name: str, email: str, password_hash: str, role: Role) -> User:
        user = User(name=name, email=email, password_hash=password_hash, role=role)
        self.session.add(user)
        self.session.flush()
        return user
