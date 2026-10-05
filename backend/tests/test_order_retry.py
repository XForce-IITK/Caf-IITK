"""NFR-4: transient deadlock and serialisation failures are retried at most 3 times."""

from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.modules.ordering.retry import MAX_RETRIES, TransientFailureError, run_in_transaction


class _PgError(Exception):
    def __init__(self, sqlstate: str) -> None:
        self.sqlstate = sqlstate


def _db_error(sqlstate: str) -> OperationalError:
    return OperationalError("SELECT 1", {}, _PgError(sqlstate))


@pytest.fixture
def session(engine: Engine) -> Iterator[Session]:
    with Session(engine) as session:
        yield session


class _FailsFirst:
    def __init__(self, session: Session, failures: int, sqlstate: str) -> None:
        self.session = session
        self.failures = failures
        self.sqlstate = sqlstate
        self.calls = 0

    def __call__(self) -> int:
        self.calls += 1
        value = self.session.scalar(text("SELECT 7"))
        if self.calls <= self.failures:
            raise _db_error(self.sqlstate)
        assert isinstance(value, int)
        return value


@pytest.mark.parametrize("sqlstate", ["40P01", "40001"])
def test_transient_failure_is_retried_with_back_off(session: Session, sqlstate: str) -> None:
    work = _FailsFirst(session, failures=MAX_RETRIES, sqlstate=sqlstate)
    slept: list[float] = []

    assert run_in_transaction(session, work, sleep=slept.append) == 7

    assert work.calls == MAX_RETRIES + 1
    assert len(slept) == MAX_RETRIES
    # Jittered: each wait is drawn from a window that doubles per attempt.
    assert all(0 <= wait <= 0.02 * 2**attempt for attempt, wait in enumerate(slept))
    assert not session.in_transaction()


def test_gives_up_after_three_retries(session: Session) -> None:
    work = _FailsFirst(session, failures=MAX_RETRIES + 1, sqlstate="40P01")

    with pytest.raises(TransientFailureError):
        run_in_transaction(session, work, sleep=lambda _: None)

    assert work.calls == MAX_RETRIES + 1
    assert not session.in_transaction()


def test_other_database_errors_are_not_retried(session: Session) -> None:
    # 23514 is check_violation: a real bug, never worth repeating.
    work = _FailsFirst(session, failures=1, sqlstate="23514")

    with pytest.raises(OperationalError):
        run_in_transaction(session, work, sleep=lambda _: None)

    assert work.calls == 1
