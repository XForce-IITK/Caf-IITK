from collections.abc import Iterator

import pytest
from sqlalchemy import text

from app.core.config import get_settings
from app.db.session import get_engine, get_session, get_sessionmaker


@pytest.fixture
def configured_database(database_url: str, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("CAF_DATABASE_URL", database_url)
    for cached in (get_settings, get_engine, get_sessionmaker):
        cached.cache_clear()
    yield
    get_engine().dispose()
    for cached in (get_settings, get_engine, get_sessionmaker):
        cached.cache_clear()


@pytest.mark.usefixtures("configured_database")
def test_get_session_yields_a_working_session() -> None:
    sessions = get_session()
    session = next(sessions)
    assert session.execute(text("SELECT 1")).scalar_one() == 1
    sessions.close()
