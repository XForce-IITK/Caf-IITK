"""Engine and session factory.

Services own transactions (`with session.begin(): ...`); only repositories
issue SQL. Routers receive a session through the `get_session` dependency.
"""

from collections.abc import Generator
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


@lru_cache
def get_engine() -> Engine:
    return create_engine(get_settings().database_url, pool_pre_ping=True)


@lru_cache
def get_sessionmaker() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), expire_on_commit=False)


def get_session() -> Generator[Session]:
    session = get_sessionmaker()()
    try:
        yield session
    finally:
        session.close()
