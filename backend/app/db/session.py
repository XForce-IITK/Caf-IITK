"""Engine and session factory.

Services own transactions (`with session.begin(): ...`); only repositories
issue SQL. Routers receive a session through the `get_session` dependency.
"""

from collections.abc import Generator
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

# NFR-16: while the database is down a request must fail within 5 s, not hang.
# libpq applies the connect timeout to each address a host name resolves to, and
# `localhost` is both ::1 and 127.0.0.1, so two attempts must fit in that budget.
# The pool wait keeps SQLAlchemy's 30 s default: a full pool is a rush (NFR-1), not an
# outage, and while the database is down each attempt gives its connection back
# within the connect timeout anyway.
CONNECT_TIMEOUT_S = 2


@lru_cache
def get_engine() -> Engine:
    # pool_pre_ping drops connections the database closed while it was away, so
    # service resumes on its own once it is back.
    return create_engine(
        get_settings().database_url,
        pool_pre_ping=True,
        connect_args={"connect_timeout": CONNECT_TIMEOUT_S},
    )


@lru_cache
def get_sessionmaker() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), expire_on_commit=False)


def get_session() -> Generator[Session]:
    session = get_sessionmaker()()
    try:
        yield session
    finally:
        session.close()
