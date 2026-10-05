"""Shared fixtures. Database tests run against real PostgreSQL 16 (NFR-37).

A single container is started per test session and migrated to head with
Alembic, so tests exercise the same schema as production.
"""

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine
from testcontainers.community.postgres import PostgresContainer

from app.main import create_app
from app.mockpay.main import create_app as create_mockpay_app

BACKEND_DIR = Path(__file__).resolve().parent.parent

# A full-length signing key, so tests exercise JWTs as configured in production.
os.environ.setdefault("CAF_JWT_SECRET", "test-secret-" + "x" * 32)

# Colima (macOS) exposes Docker on a per-user socket; point testcontainers at it.
_colima_socket = Path.home() / ".colima" / "default" / "docker.sock"
if "DOCKER_HOST" not in os.environ and _colima_socket.exists():
    os.environ["DOCKER_HOST"] = f"unix://{_colima_socket}"
    os.environ.setdefault("TESTCONTAINERS_DOCKER_SOCKET_OVERRIDE", "/var/run/docker.sock")


@pytest.fixture(scope="session")
def database_url() -> Iterator[str]:
    with PostgresContainer("postgres:16", driver="psycopg") as postgres:
        url = postgres.get_connection_url()
        config = Config(str(BACKEND_DIR / "alembic.ini"))
        config.set_main_option("sqlalchemy.url", url)
        command.upgrade(config, "head")
        yield url


@pytest.fixture(scope="session")
def engine(database_url: str) -> Iterator[Engine]:
    engine = create_engine(database_url)
    yield engine
    engine.dispose()


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


@pytest.fixture
def mockpay_client() -> TestClient:
    return TestClient(create_mockpay_app())


@pytest.fixture
def db_client(engine: Engine) -> Iterator[TestClient]:
    """An API client whose requests use the test database; tables are emptied afterwards."""
    from sqlalchemy import text
    from sqlalchemy.orm import Session, sessionmaker

    from app.db.session import get_session

    factory = sessionmaker(bind=engine, expire_on_commit=False)

    def override_get_session() -> Iterator[Session]:
        with factory() as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_session] = override_get_session
    yield TestClient(app)
    with engine.begin() as connection:
        # Every business table hangs off one of these; settings keep their seeded defaults.
        connection.execute(text("TRUNCATE users, menu_items, service_days, discount_rules CASCADE"))


@pytest.fixture
def configured_database(database_url: str, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Point the app's own settings, engine and sessionmaker at the test database."""
    from app.core.config import get_settings
    from app.db.session import get_engine, get_sessionmaker

    monkeypatch.setenv("CAF_DATABASE_URL", database_url)
    for cached in (get_settings, get_engine, get_sessionmaker):
        cached.cache_clear()
    yield
    get_engine().dispose()
    for cached in (get_settings, get_engine, get_sessionmaker):
        cached.cache_clear()


@pytest.fixture(scope="session")
def mockpay_url() -> Iterator[str]:
    """mockpay served by uvicorn on a free local port, so timeouts are real (ADR-05).

    Timeout mode holds a request for 1 s; tests give the gateway a shorter timeout.
    """
    import socket
    import threading
    import time

    import uvicorn

    from app.core.config import Settings

    app = create_mockpay_app(Settings(env="test", mockpay_hang_s=1.0))
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    server = uvicorn.Server(uvicorn.Config(app, log_level="warning", timeout_graceful_shutdown=2))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
    thread.start()
    while not server.started:
        time.sleep(0.01)
    yield f"http://127.0.0.1:{listener.getsockname()[1]}"
    server.should_exit = True
    thread.join(timeout=5)
