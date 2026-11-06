"""US-32 (NFR-16) acceptance tests TC-US32-AC1..AC2: the database goes down and comes back.

These tests kill and restart PostgreSQL, so they use a container of their own on a
fixed host port (the shared test database must stay up). The app is pointed at it
through its own settings, so the engine's real timeouts and pool are exercised.
"""

import socket
import threading
import time
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import timedelta
from typing import Annotated, Any

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from conftest import BACKEND_DIR
from fastapi import Depends
from fastapi.testclient import TestClient
from loadgen import Scenario, menu_open_all_day, seed
from sqlalchemy import Engine, create_engine, select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session
from testcontainers.community.postgres import PostgresContainer

from app.core import clock
from app.core.errors import _connection_lost
from app.db.session import get_engine, get_session, get_sessionmaker
from app.main import create_app
from app.models.enums import OrderStatus
from app.models.ordering import Order
from app.modules.ordering.sweeper import HoldSweeper
from app.modules.payments.fake import FakePaymentGateway
from app.modules.payments.gateway import AuthResult, PaymentGateway, TransactionGuardedGateway
from app.modules.payments.mockpay_gateway import get_payment_gateway
from app.worker.jobs import Job
from app.worker.main import Worker

pytestmark = pytest.mark.usefixtures("outage_settings")

URL = "/api/v1/orders"
# NFR-16
ANSWER_WITHIN_S = 5
RESUME_WITHIN_S = 30


@dataclass
class OutageDatabase:
    container: PostgresContainer
    url: str

    def kill(self) -> None:
        # SIGKILL, as in a crash: a SIGTERM would wait for the pool's idle connections.
        self.container.get_wrapped_container().kill()

    def start(self) -> None:
        self.container.get_wrapped_container().start()
        plain = self.url.replace("postgresql+psycopg://", "postgresql://")
        deadline = time.monotonic() + 60
        while True:
            try:
                psycopg.connect(plain, connect_timeout=1).close()
                return
            except psycopg.OperationalError:
                if time.monotonic() > deadline:
                    raise
                time.sleep(0.2)


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port: int = sock.getsockname()[1]
        return port


@pytest.fixture(scope="module")
def outage_db() -> Iterator[OutageDatabase]:
    # A fixed host port, so the database is at the same address after a restart.
    container = PostgresContainer("postgres:16", driver="psycopg").with_bind_ports(
        5432, _free_port()
    )
    with container:
        # One address, as for `db` in Compose or an RDS endpoint; `localhost` is two,
        # and libpq waits out the connect timeout on each of them in turn.
        url = container.get_connection_url().replace("@localhost:", "@127.0.0.1:")
        config = Config(str(BACKEND_DIR / "alembic.ini"))
        config.set_main_option("sqlalchemy.url", url)
        command.upgrade(config, "head")
        yield OutageDatabase(container, url)


@pytest.fixture
def outage_settings(outage_db: OutageDatabase, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    from app.core.config import get_settings

    monkeypatch.setenv("CAF_DATABASE_URL", outage_db.url)
    for cached in (get_settings, get_engine, get_sessionmaker):
        cached.cache_clear()
    yield
    get_engine().dispose()
    for cached in (get_settings, get_engine, get_sessionmaker):
        cached.cache_clear()


@pytest.fixture
def side_engine(outage_db: OutageDatabase) -> Iterator[Engine]:
    """Seeds and inspects the database from outside the app under test."""
    engine = create_engine(outage_db.url, pool_pre_ping=True)
    yield engine
    engine.dispose()


@pytest.fixture
def scenario(side_engine: Engine) -> Iterator[Scenario]:
    with menu_open_all_day(side_engine):
        yield seed(side_engine, requests=1, portions=5, seats=5)


def _client(gateway: PaymentGateway) -> TestClient:
    """The app as deployed, with `gateway` behind the NFR-6 guard."""

    def guarded(session: Annotated[Session, Depends(get_session)]) -> PaymentGateway:
        return TransactionGuardedGateway(gateway, session)

    app = create_app()
    app.dependency_overrides[get_payment_gateway] = guarded
    return TestClient(app)


def _order_body(client: TestClient, scenario: Scenario) -> dict[str, Any]:
    cart = {
        "slot_id": str(scenario.slot_id),
        "lines": [{"item_id": str(scenario.item_id), "qty": 1}],
    }
    quote = client.post("/api/v1/quotes", json=cart, headers=_auth(scenario))
    assert quote.status_code == 200, quote.text
    return cart | {"quoted_payable_paise": quote.json()["payable_paise"]}


def _auth(scenario: Scenario) -> dict[str, str]:
    return {"Authorization": f"Bearer {scenario.tokens[0]}"}


def _place(client: TestClient, scenario: Scenario, body: dict[str, Any]) -> Any:
    headers = _auth(scenario) | {"Idempotency-Key": uuid.uuid4().hex}
    return client.post(URL, json=body, headers=headers)


def _orders(engine: Engine, scenario: Scenario) -> list[OrderStatus]:
    with Session(engine) as session:
        return list(session.scalars(select(Order.status).where(Order.slot_id == scenario.slot_id)))


def _counters(engine: Engine, scenario: Scenario) -> tuple[int, int]:
    with engine.connect() as c:
        allocated = c.execute(
            text("SELECT allocated FROM daily_inventory WHERE item_id = :i"),
            {"i": scenario.item_id},
        ).scalar_one()
        booked = c.execute(
            text("SELECT booked FROM slots WHERE id = :s"), {"s": scenario.slot_id}
        ).scalar_one()
    return allocated, booked


def test_tc_us32_ac1_database_stopped_gives_503_with_retry_after_within_5_s(
    outage_db: OutageDatabase, side_engine: Engine, scenario: Scenario
) -> None:
    client = _client(FakePaymentGateway())
    body = _order_body(client, scenario)  # the pool now holds a live connection
    outage_db.kill()
    try:
        started = time.monotonic()
        response = _place(client, scenario, body)
        elapsed = time.monotonic() - started
    finally:
        outage_db.start()

    assert response.status_code == 503, response.text
    assert response.headers["Retry-After"] == "5"
    assert "try again" in response.json()["detail"]
    assert elapsed < ANSWER_WITHIN_S
    assert _orders(side_engine, scenario) == []
    assert _counters(side_engine, scenario) == (0, 0)


class KillDuringPayment(FakePaymentGateway):
    """The database dies while the payment call is out (after reserve committed)."""

    def __init__(self, database: OutageDatabase) -> None:
        super().__init__()
        self.database = database

    def authorise(self, reference: str, amount_paise: int) -> AuthResult:
        result = super().authorise(reference, amount_paise)
        self.database.kill()
        return result


def test_tc_us32_ac1_dying_mid_order_leaves_only_a_hold_the_sweeper_releases(
    outage_db: OutageDatabase, side_engine: Engine, scenario: Scenario
) -> None:
    client = _client(KillDuringPayment(outage_db))
    body = _order_body(client, scenario)
    try:
        started = time.monotonic()
        response = _place(client, scenario, body)
        elapsed = time.monotonic() - started
    finally:
        outage_db.start()

    assert response.status_code == 503, response.text
    assert response.headers["Retry-After"] == "5"
    assert elapsed < ANSWER_WITHIN_S
    # The confirm transaction never committed: the order is still only a timed hold.
    assert _orders(side_engine, scenario) == [OrderStatus.PENDING_PAYMENT]
    assert _counters(side_engine, scenario) == (1, 1)

    with Session(side_engine, expire_on_commit=False) as session:
        HoldSweeper(session, hold_expiry_s=120).sweep(clock.now() + timedelta(seconds=121))
    assert _orders(side_engine, scenario) == [OrderStatus.PAYMENT_FAILED]
    assert _counters(side_engine, scenario) == (0, 0)


def test_tc_us32_ac2_ordering_resumes_within_30_s_of_a_restart_without_an_app_restart(
    outage_db: OutageDatabase, side_engine: Engine, scenario: Scenario
) -> None:
    client = _client(FakePaymentGateway())
    body = _order_body(client, scenario)
    outage_db.kill()
    try:
        assert _place(client, scenario, body).status_code == 503
    finally:
        outage_db.start()

    restarted = time.monotonic()
    while (response := _place(client, scenario, body)).status_code == 503:
        assert time.monotonic() - restarted < RESUME_WITHIN_S, "still 503 30 s after the restart"
        time.sleep(1)
    assert response.status_code == 201, response.text
    assert _orders(side_engine, scenario) == [OrderStatus.ACCEPTED]


def test_a_worker_waits_out_an_outage_then_becomes_leader(outage_db: OutageDatabase) -> None:
    ran = threading.Event()
    worker = Worker(
        get_engine(), [Job("probe", ran.set, every_s=60, run_at_startup=True)], retry_s=0.2
    )
    stop = threading.Event()
    outage_db.kill()
    thread = threading.Thread(target=worker.run, args=(stop,))
    thread.start()
    try:
        time.sleep(1)
        assert thread.is_alive() and not worker.is_leader
        outage_db.start()
        deadline = time.monotonic() + RESUME_WITHIN_S
        while not worker.is_leader:
            assert time.monotonic() < deadline, "no leader 30 s after the restart"
            time.sleep(0.2)
        assert ran.is_set()
    finally:
        outage_db.start()
        stop.set()
        thread.join(timeout=10)


class _PgError(Exception):
    def __init__(self, sqlstate: str | None) -> None:
        self.sqlstate = sqlstate


@pytest.mark.parametrize(
    ("sqlstate", "lost"),
    [(None, True), ("08006", True), ("57P01", True), ("55P03", False), ("57014", False)],
)
def test_only_connection_failures_count_as_the_database_being_down(
    sqlstate: str | None, lost: bool
) -> None:
    error = OperationalError("SELECT 1", {}, _PgError(sqlstate))
    assert _connection_lost(error) is lost


def test_a_statement_error_is_not_turned_into_a_503() -> None:
    """A lock timeout (55P03) is a bug or contention, not an outage: it stays a 500."""
    app = create_app()

    @app.get("/boom")
    def boom() -> None:
        raise OperationalError("SELECT 1", {}, _PgError("55P03"))

    response = TestClient(app, raise_server_exceptions=False).get("/boom")
    assert response.status_code == 500
