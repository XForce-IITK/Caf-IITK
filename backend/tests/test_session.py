import pytest
from sqlalchemy import text

from app.db.session import get_session


@pytest.mark.usefixtures("configured_database")
def test_get_session_yields_a_working_session() -> None:
    sessions = get_session()
    session = next(sessions)
    assert session.execute(text("SELECT 1")).scalar_one() == 1
    sessions.close()
