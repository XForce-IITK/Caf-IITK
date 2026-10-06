"""Deployment-time seed of the first Administrator and a Kitchen account (FR-2)."""

from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, select, text
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.security import verify_password
from app.models.enums import Role
from app.models.identity import User
from app.seed import main, seed

CONFIGURED = Settings(
    seed_admin_email="Admin@iitk.ac.in",
    seed_admin_password="admin-password",
    seed_kitchen_email="kitchen@iitk.ac.in",
    seed_kitchen_password="kitchen-password",
)


@pytest.fixture
def clean_users(configured_database: None, engine: Engine) -> Iterator[None]:
    yield
    with engine.begin() as connection:
        connection.execute(text("TRUNCATE users CASCADE"))


@pytest.mark.usefixtures("clean_users")
def test_seed_creates_admin_and_kitchen_accounts(engine: Engine) -> None:
    assert seed(CONFIGURED) == ["ADMIN: created", "KITCHEN: created"]

    with Session(engine) as session:
        users = {u.email: u for u in session.scalars(select(User))}
    assert users["admin@iitk.ac.in"].role == Role.ADMIN
    assert users["kitchen@iitk.ac.in"].role == Role.KITCHEN
    assert verify_password(users["admin@iitk.ac.in"].password_hash, "admin-password")


@pytest.mark.usefixtures("clean_users")
def test_seed_is_idempotent(engine: Engine) -> None:
    seed(CONFIGURED)

    assert seed(CONFIGURED) == ["ADMIN: already exists", "KITCHEN: already exists"]
    with Session(engine) as session:
        assert len(session.scalars(select(User)).all()) == 2


@pytest.mark.usefixtures("clean_users")
def test_unconfigured_accounts_are_skipped(capsys: pytest.CaptureFixture[str]) -> None:
    assert seed(Settings()) == [
        "ADMIN: skipped (not configured)",
        "KITCHEN: skipped (not configured)",
    ]
    main()
    assert "skipped" in capsys.readouterr().out


@pytest.mark.usefixtures("clean_users")
def test_short_seed_password_is_refused() -> None:
    with pytest.raises(SystemExit):
        seed(Settings(seed_admin_email="admin@iitk.ac.in", seed_admin_password="short"))
