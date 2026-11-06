"""Engine and session factory.

Services own transactions (`with session.begin(): ...`); only repositories
issue SQL. Routers receive a session through the `get_session` dependency.

Every transaction a session begins runs as the caf_app role (migration 0005), so
PostgreSQL refuses any UPDATE or DELETE of an audit entry (NFR-26, FR-48).
"""

from collections.abc import Generator
from functools import lru_cache
from typing import Any

from sqlalchemy import Connection, Engine, create_engine, event
from sqlalchemy.orm import Session, SessionTransaction, sessionmaker

from app.core.config import get_settings

# NFR-16: while the database is down a request must fail within 5 s, not hang.
# libpq applies the connect timeout to each address a host name resolves to, and
# `localhost` is both ::1 and 127.0.0.1, so two attempts must fit in that budget.
# The pool wait keeps SQLAlchemy's 30 s default: a full pool is a rush (NFR-1), not an
# outage, and while the database is down each attempt gives its connection back
# within the connect timeout anyway.
CONNECT_TIMEOUT_S = 2

# The application's database role: all it needs, but only INSERT and SELECT on
# audit_log. The agent's repository narrows it further to caf_agent (NFR-25).
APP_ROLE = "caf_app"


def run_as_app_role(factory: sessionmaker[Session]) -> sessionmaker[Session]:
    """Make every transaction the factory's sessions begin run as APP_ROLE.

    SET LOCAL lasts until the transaction ends, so a pooled connection never
    carries the role into work that is not a session's.
    """

    @event.listens_for(factory, "after_begin")
    def _set_role(session: Session, transaction: SessionTransaction, conn: Connection) -> Any:
        conn.exec_driver_sql(f"SET LOCAL ROLE {APP_ROLE}")

    return factory


@lru_cache
def get_engine() -> Engine:
    # pool_pre_ping drops connections the database closed while it was away, so
    # service resumes on its own once it is back.
    #
    # A fixed pool with no overflow (CAFIITK-189). Overflow connections are closed as
    # soon as they are returned, so under load nearly every checkout opened a new one:
    # a TCP handshake, a forked backend and a SCRAM exchange each time (442 new
    # connections in 30 s of reads, against 20 now). A request holds one connection
    # at a time, so with no overflow the extra requests simply wait in the pool's queue.
    settings = get_settings()
    return create_engine(
        settings.database_url,
        pool_pre_ping=True,
        pool_size=settings.db_pool_size,
        max_overflow=0,
        connect_args={"connect_timeout": CONNECT_TIMEOUT_S},
    )


@lru_cache
def get_sessionmaker() -> sessionmaker[Session]:
    return run_as_app_role(sessionmaker(bind=get_engine(), expire_on_commit=False))


def get_session() -> Generator[Session]:
    session = get_sessionmaker()()
    try:
        yield session
    finally:
        session.close()
