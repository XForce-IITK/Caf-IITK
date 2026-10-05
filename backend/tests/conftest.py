"""Shared fixtures. Database tests run against real PostgreSQL 16 (NFR-37).

A single container is started per test session and migrated to head with
Alembic, so tests exercise the same schema as production.
"""

import os
import signal
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import httpx
import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine
from testcontainers.community.postgres import PostgresContainer

from app.core.config import get_settings
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


@dataclass(frozen=True)
class LiveStack:
    # One URL per caf-api process.
    api_urls: tuple[str, ...]
    mockpay_url: str


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port: int = sock.getsockname()[1]
        return port


def _serve(app: str, url: str, env: dict[str, str]) -> subprocess.Popen[bytes]:
    port = url.rsplit(":", 1)[1]
    command = [sys.executable, "-m", "uvicorn", app, "--host", "127.0.0.1", "--port", port]
    command += ["--log-level", "warning"]
    # Its own process group, so it can be stopped without touching the test run.
    if sys.platform == "win32":
        return subprocess.Popen(
            command, cwd=BACKEND_DIR, env=env, creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
        )
    return subprocess.Popen(command, cwd=BACKEND_DIR, env=env, start_new_session=True)


def _stop(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    if sys.platform == "win32":
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(process.pid)], capture_output=True, check=False
        )
    else:
        os.killpg(process.pid, signal.SIGTERM)
    process.wait(timeout=20)


def _wait_until_healthy(url: str, process: subprocess.Popen[bytes], timeout_s: float = 60) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"{url} exited with code {process.returncode} during start-up")
        try:
            if httpx.get(f"{url}/health", timeout=2).status_code == httpx.codes.OK:
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.2)
    raise RuntimeError(f"{url} was not healthy within {timeout_s} s")


@pytest.fixture(scope="session")
def live_stack(database_url: str) -> Iterator[LiveStack]:
    """Two caf-api processes plus mockpay, serving the test database.

    Concurrency tests that must hold across processes (NFR-13) send real HTTP here
    instead of using the in-process TestClient. Each API process has its own port:
    `uvicorn --workers` shares one listening socket, which drops responses on Windows.
    """
    stack = LiveStack(
        api_urls=tuple(f"http://127.0.0.1:{_free_port()}" for _ in range(2)),
        mockpay_url=f"http://127.0.0.1:{_free_port()}",
    )
    env = os.environ | {
        "CAF_ENV": "test",
        "CAF_DATABASE_URL": database_url,
        "CAF_MOCKPAY_URL": stack.mockpay_url,
        # The secret this process signs test tokens with, whatever the environment says.
        "CAF_JWT_SECRET": get_settings().jwt_secret,
    }
    processes: list[subprocess.Popen[bytes]] = []
    try:
        # mockpay keeps its ledger in memory, so it is always one process.
        servers = [("app.mockpay.main:app", stack.mockpay_url)]
        servers += [("app.main:app", url) for url in stack.api_urls]
        for app, url in servers:
            process = _serve(app, url, env)
            processes.append(process)
            _wait_until_healthy(url, process)
        yield stack
    finally:
        for process in reversed(processes):
            _stop(process)


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
