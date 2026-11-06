"""NFR-3 and NFR-6 test cases TC-NFR3 and TC-NFR6: failure injection.

TC-NFR3: each operation is run once for every SQL statement it issues, with a fault
injected at that statement. After each fault two things must hold:

1. The whole database is exactly as it was when the faulted transaction began:
   nothing of it was written, and nothing else was committed after it.
2. An operation of several transactions (reserve, authorise, confirm) may stop at a
   committed boundary, but only at one the system recovers from. Once the hold
   sweeper and the payment outbox have run, every counter matches the orders that
   hold it, and no order, modification or payment is left pending.

TC-NFR6: the payment gateway and the LLM provider are wrapped in spies that record
whether any connection of the application's engine was checked out when they were
called. A checked-out connection is an open transaction (SQLAlchemy 2.0 holds a
connection only while a transaction is open), so every call must find none.
"""

import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from typing import Annotated, Any, cast
from zoneinfo import ZoneInfo

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from loadgen import check_counters
from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import QueuePool

from app.core import clock
from app.core.security import create_access_token
from app.db.session import get_session
from app.models.agent import AgentRun, Proposal
from app.models.capacity import DailyInventory, Slot
from app.models.catalogue import MenuItem
from app.models.enums import (
    AgentRunStatus,
    AgentSource,
    AgentTrigger,
    ItemCategory,
    ProposalType,
    Role,
)
from app.models.identity import User
from app.modules.agent.llm import (
    CircuitBreaker,
    GuardedLLMClient,
    LLMProviderError,
    LLMRequest,
    LLMResponse,
    ResponseCache,
)
from app.modules.agent.service import AgentService
from app.modules.ordering.outbox import OutboxDeliverer
from app.modules.ordering.sweeper import HoldSweeper
from app.modules.payments.fake import FakePaymentGateway
from app.modules.payments.gateway import (
    AuthOutcome,
    AuthResult,
    PaymentGateway,
    TransactionGuardedGateway,
)
from app.modules.payments.mockpay_gateway import get_payment_gateway

IST = ZoneInfo("Asia/Kolkata")
DAY = date(2026, 10, 6)
# After P-MENU_OPEN (08:00), before the first slot's cut-off.
NOW = datetime(2026, 10, 6, 9, 0, tzinfo=IST)
THALI, TEA = 8000, 1500
HOLD_EXPIRY_S = 120


class InjectedFault(Exception):
    """Raised in place of the Nth SQL statement."""


Snapshot = dict[str, list[str]]


def _business_tables(connection: Any) -> list[str]:
    """Every table but the schema version and the seeded settings."""
    return list(
        connection.execute(
            text(
                "SELECT tablename FROM pg_tables WHERE schemaname = 'public' "
                "AND tablename NOT IN ('alembic_version', 'settings')"
            )
        ).scalars()
    )


def snapshot(engine: Engine) -> Snapshot:
    """Every row of every table, as text, in a stable order."""
    with engine.connect() as connection:
        tables = connection.execute(
            text(
                "SELECT tablename FROM pg_tables "
                "WHERE schemaname = 'public' AND tablename <> 'alembic_version'"
            )
        ).scalars()
        return {
            table: sorted(
                repr(tuple(row)) for row in connection.execute(text(f'SELECT * FROM "{table}"'))
            )
            for table in tables
        }


def _diff(before: Snapshot, after: Snapshot) -> dict[str, dict[str, list[str]]]:
    changed = {}
    for table in sorted(before.keys() | after.keys()):
        old, new = set(before.get(table, [])), set(after.get(table, []))
        if old != new:
            changed[table] = {"removed": sorted(old - new), "added": sorted(new - old)}
    return changed


@dataclass
class FaultInjector:
    """Fails the Nth statement on `engine`; remembers the database as its transaction began.

    A dry run first records which transaction each statement belongs to, so a faulted
    run snapshots the database only as the transaction it will fail begins.
    """

    engine: Engine
    observer: Engine
    recording: bool = False
    fail_at: int | None = None
    snapshot_at: int | None = None
    count: int = 0
    begins: int = 0
    transaction_of: list[int] = field(default_factory=list)
    fired_sql: str | None = None
    at_begin: Snapshot | None = None
    expected: Snapshot | None = None

    def __post_init__(self) -> None:
        event.listen(self.engine, "begin", self._on_begin)
        event.listen(self.engine, "before_cursor_execute", self._on_statement)

    def remove(self) -> None:
        event.remove(self.engine, "begin", self._on_begin)
        event.remove(self.engine, "before_cursor_execute", self._on_statement)

    def record(self) -> None:
        self.recording, self.begins, self.transaction_of = True, 0, []

    def arm(self, n: int) -> None:
        self.fail_at, self.snapshot_at = n, self.transaction_of[n - 1]
        self.count, self.begins = 0, 0
        self.fired_sql, self.at_begin, self.expected = None, None, None

    def disarm(self) -> None:
        self.recording, self.fail_at = False, None

    def _on_begin(self, _connection: Any) -> None:
        if self.recording or self.fail_at is not None:
            self.begins += 1
        if self.fail_at is not None and self.begins == self.snapshot_at:
            self.at_begin = snapshot(self.observer)

    def _on_statement(self, _conn: Any, _cursor: Any, statement: str, *_: Any) -> None:
        if self.recording:
            self.transaction_of.append(self.begins)
        if self.fail_at is None or self.expected is not None:
            return
        self.count += 1
        if self.count == self.fail_at:
            assert self.at_begin is not None, "the statements differ from the dry run's"
            self.fired_sql = statement
            self.expected = self.at_begin
            raise InjectedFault(statement)


@pytest.fixture
def observer(database_url: str) -> Iterator[Engine]:
    """Reads the database for snapshots, unseen by the injector."""
    engine = create_engine(database_url)
    yield engine
    engine.dispose()


@pytest.fixture
def faults(engine: Engine, observer: Engine) -> Iterator[FaultInjector]:
    injector = FaultInjector(engine, observer)
    yield injector
    injector.remove()


@dataclass
class NoTransactionSpy:
    """Records, for each external call, whether the app's engine had a connection out."""

    engine: Engine
    calls: list[tuple[str, int]] = field(default_factory=list)

    def check(self, what: str) -> None:
        self.calls.append((what, cast(QueuePool, self.engine.pool).checkedout()))

    @property
    def violations(self) -> list[tuple[str, int]]:
        return [(what, out) for what, out in self.calls if out]


@dataclass
class SpyGateway:
    inner: PaymentGateway
    spy: NoTransactionSpy

    def authorise(self, reference: str, amount_paise: int) -> AuthResult:
        self.spy.check("authorise")
        return self.inner.authorise(reference, amount_paise)

    def void(self, reference: str) -> None:
        self.spy.check("void")
        self.inner.void(reference)

    def refund(self, reference: str, auth_reference: str, amount_paise: int) -> None:
        self.spy.check("refund")
        self.inner.refund(reference, auth_reference, amount_paise)


class Crash(Exception):
    """The process dies while the payment call is out."""


class CrashOnAuthorise(FakePaymentGateway):
    def authorise(self, reference: str, amount_paise: int) -> AuthResult:
        raise Crash


@pytest.fixture
def spy(engine: Engine) -> NoTransactionSpy:
    return NoTransactionSpy(engine)


@dataclass
class Cafe:
    """A Student, an Administrator, Thali and Tea, and two slots, all new each time."""

    engine: Engine
    api: TestClient
    gateway: FakePaymentGateway

    def __post_init__(self) -> None:
        self.student = self._user(Role.STUDENT)
        self.admin = self._user(Role.ADMIN)
        suffix = uuid.uuid4().hex[:8]
        self.thali = MenuItem(
            id=uuid.uuid4(), name=f"Thali {suffix}", category=ItemCategory.MEAL, price_paise=THALI
        )
        self.tea = MenuItem(
            id=uuid.uuid4(), name=f"Tea {suffix}", category=ItemCategory.BEVERAGE, price_paise=TEA
        )
        self.slots = [
            Slot(
                id=uuid.uuid4(),
                service_date=DAY,
                starts_at=datetime(2026, 10, 6, 12, 15, tzinfo=IST) + timedelta(minutes=m),
                ends_at=datetime(2026, 10, 6, 12, 30, tzinfo=IST) + timedelta(minutes=m),
                capacity=30,
            )
            for m in (0, 15)
        ]
        self._add(self.thali, self.tea)
        self._add(
            *self.slots,
            DailyInventory(item_id=self.thali.id, service_date=DAY, total=10),
            DailyInventory(item_id=self.tea.id, service_date=DAY, total=10),
        )

    def _add(self, *rows: Any) -> None:
        with Session(self.engine, expire_on_commit=False) as session, session.begin():
            session.add_all(rows)

    def _user(self, role: Role) -> User:
        user = User(
            id=uuid.uuid4(),
            name=f"{role.value} user",
            email=f"{uuid.uuid4().hex[:8]}@iitk.ac.in",
            password_hash="unused",
            role=role,
        )
        self._add(user)
        return user

    def headers(self, user: User) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {create_access_token(user.id, user.role)}",
            "Idempotency-Key": uuid.uuid4().hex,
        }

    def cart(self, teas: int = 2, slot: int = 0) -> dict[str, Any]:
        lines = [{"item_id": str(self.thali.id), "qty": 1}]
        if teas:
            lines.append({"item_id": str(self.tea.id), "qty": teas})
        return {"slot_id": str(self.slots[slot].id), "lines": lines}

    def place(self, teas: int = 2) -> Any:
        body = self.cart(teas) | {"quoted_payable_paise": THALI + teas * TEA}
        return self.api.post("/api/v1/orders", json=body, headers=self.headers(self.student))

    def placed(self) -> dict[str, Any]:
        response = self.place()
        assert response.status_code == 201, response.text
        order: dict[str, Any] = response.json()
        return order

    def modify(self, order: dict[str, Any], teas: int, slot: int = 0) -> Any:
        body = self.cart(teas, slot) | {
            "version": order["version"],
            "quoted_payable_paise": THALI + teas * TEA,
        }
        return self.api.patch(
            f"/api/v1/orders/{order['id']}", json=body, headers=self.headers(self.student)
        )

    def cancel(self, order: dict[str, Any]) -> Any:
        return self.api.post(
            f"/api/v1/orders/{order['id']}/cancel",
            json={"version": order["version"]},
            headers=self.headers(self.student),
        )

    def admin_cancel(self, order: dict[str, Any]) -> Any:
        return self.api.post(
            f"/api/v1/admin/orders/{order['id']}/cancel",
            json={"version": order["version"], "reason": "Wrong item packed"},
            headers=self.headers(self.admin),
        )

    def replenish_proposal(self) -> uuid.UUID:
        run = AgentRun(
            id=uuid.uuid4(),
            trigger=AgentTrigger.ON_DEMAND,
            requested_by=self.admin.id,
            status=AgentRunStatus.SUCCEEDED,
            source=AgentSource.LLM,
        )
        proposal = Proposal(
            id=uuid.uuid4(),
            run_id=run.id,
            type=ProposalType.REPLENISH,
            target_date=DAY,
            payload={
                "lines": [
                    {"item_id": str(self.thali.id), "additional_portions": 5},
                    {"item_id": str(self.tea.id), "additional_portions": 5},
                ]
            },
            rationale="Forecast shows a stock-out by 13:00",
            source=AgentSource.LLM,
            expires_at=datetime(2026, 10, 6, 12, 0, tzinfo=IST),
            created_at=NOW - timedelta(minutes=30),
        )
        self._add(run)
        self._add(proposal)
        return proposal.id

    def approve(self, proposal_id: uuid.UUID) -> Any:
        return self.api.post(
            f"/api/v1/admin/proposals/{proposal_id}/approve", headers=self.headers(self.admin)
        )


@pytest.fixture
def make_cafe(
    db_client: TestClient,
    engine: Engine,
    spy: NoTransactionSpy,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[Callable[..., Cafe]]:
    """A Cafe behind an API whose unhandled errors come back as 500, not raised."""
    monkeypatch.setattr(clock, "now", lambda: NOW)
    app: FastAPI = db_client.app  # type: ignore[assignment]
    api = TestClient(app, raise_server_exceptions=False)

    def make(gateway: FakePaymentGateway | None = None) -> Cafe:
        gateway = gateway or FakePaymentGateway()

        def guarded(session: Annotated[Session, Depends(get_session)]) -> PaymentGateway:
            return TransactionGuardedGateway(SpyGateway(gateway, spy), session)

        app.dependency_overrides[get_payment_gateway] = guarded
        # Each attempt starts from empty business tables, as db_client leaves them.
        with engine.begin() as connection:
            # DELETE, not TRUNCATE: on a few rows it is many times faster. Foreign-key
            # triggers are off for this transaction only, so the order does not matter.
            connection.execute(text("SET LOCAL session_replication_role = replica"))
            for table in _business_tables(connection):
                connection.execute(text(f'DELETE FROM "{table}"'))
            connection.execute(
                text(
                    "INSERT INTO service_days "
                    "(service_date, window_start, window_end, slot_len_min, default_capacity) "
                    "VALUES (:d, :s, :e, 15, 30)"
                ),
                {"d": DAY, "s": time(12, 0), "e": time(14, 30)},
            )
        return Cafe(engine, api, gateway)

    yield make
    app.dependency_overrides.pop(get_payment_gateway, None)


def recovery_problems(engine: Engine) -> list[str]:
    """Run the sweeper and the outbox, then report anything still inconsistent."""
    # Orders and holds are stamped with the database's own clock, not the patched one.
    later = datetime.now(UTC) + timedelta(seconds=HOLD_EXPIRY_S + 1)
    with Session(engine, expire_on_commit=False) as session:
        HoldSweeper(session, HOLD_EXPIRY_S).sweep(later)
        OutboxDeliverer(session, FakePaymentGateway()).deliver()
    problems = check_counters(engine)
    with engine.connect() as connection:
        for table, status in (("orders", "PENDING_PAYMENT"), ("payments", "PENDING")):
            stuck = connection.execute(
                text(f"SELECT count(*) FROM {table} WHERE status = :s"), {"s": status}
            ).scalar_one()
            if stuck:
                problems.append(f"{stuck} {table} still {status}")
    return problems


def every_fault(
    faults: FaultInjector,
    observer: Engine,
    setup: Callable[[], Any],
    operation: Callable[[Any], object],
) -> int:
    """Run `operation` once per statement, failing that statement; returns how many ran."""
    context = setup()
    faults.record()
    try:
        operation(context)
    finally:
        faults.disarm()
    statements = len(faults.transaction_of)
    for n in range(1, statements + 1):
        context = setup()
        faults.arm(n)
        try:
            operation(context)
        except InjectedFault:
            pass  # called outside the API, so the fault reaches the test
        finally:
            faults.disarm()
        assert faults.expected is not None, f"statement {n} was never reached"
        changed = _diff(faults.expected, snapshot(observer))
        assert not changed, f"fault at statement {n} ({faults.fired_sql!r}) left {changed}"
        problems = recovery_problems(faults.engine)
        assert not problems, (
            f"fault at statement {n} ({faults.fired_sql!r}): after recovery {problems}"
        )
    return statements


def test_tc_nfr3_order_creation_is_all_or_nothing(
    make_cafe: Callable[..., Cafe], faults: FaultInjector, observer: Engine
) -> None:
    statements = every_fault(faults, observer, make_cafe, lambda cafe: cafe.place())
    assert statements > 5


def test_tc_nfr3_payment_failure_release_is_all_or_nothing(
    make_cafe: Callable[..., Cafe], faults: FaultInjector, observer: Engine
) -> None:
    declined = FakePaymentGateway(outcome=AuthOutcome.DECLINED)
    statements = every_fault(faults, observer, lambda: make_cafe(declined), lambda c: c.place())
    assert statements > 5


@pytest.mark.parametrize(
    ("teas", "slot"),
    [(3, 0), (0, 0), (2, 1)],
    ids=["price-rises", "price-falls", "slot-moves"],
)
def test_tc_nfr3_order_modification_is_all_or_nothing(
    make_cafe: Callable[..., Cafe],
    faults: FaultInjector,
    observer: Engine,
    teas: int,
    slot: int,
) -> None:
    def setup() -> tuple[Cafe, dict[str, Any]]:
        cafe = make_cafe()
        return cafe, cafe.placed()

    def modify(context: tuple[Cafe, dict[str, Any]]) -> object:
        cafe, order = context
        return cafe.modify(order, teas, slot)

    assert every_fault(faults, observer, setup, modify) > 5


def test_tc_nfr3_order_cancellation_is_all_or_nothing(
    make_cafe: Callable[..., Cafe], faults: FaultInjector, observer: Engine
) -> None:
    def setup() -> tuple[Cafe, dict[str, Any]]:
        cafe = make_cafe()
        return cafe, cafe.placed()

    statements = every_fault(faults, observer, setup, lambda c: c[0].cancel(c[1]))
    assert statements > 5


def test_tc_nfr3_admin_cancellation_is_all_or_nothing(
    make_cafe: Callable[..., Cafe], faults: FaultInjector, observer: Engine
) -> None:
    def setup() -> tuple[Cafe, dict[str, Any]]:
        cafe = make_cafe()
        return cafe, cafe.placed()

    statements = every_fault(faults, observer, setup, lambda c: c[0].admin_cancel(c[1]))
    assert statements > 5


def test_tc_nfr3_hold_expiry_is_all_or_nothing(
    make_cafe: Callable[..., Cafe], faults: FaultInjector, observer: Engine, engine: Engine
) -> None:
    def setup() -> Cafe:
        cafe = make_cafe(CrashOnAuthorise())
        assert cafe.place().status_code == 500  # left as a PENDING_PAYMENT hold
        return cafe

    def sweep(_cafe: Cafe) -> object:
        with Session(engine, expire_on_commit=False) as session:
            return HoldSweeper(session, HOLD_EXPIRY_S).sweep(
                datetime.now(UTC) + timedelta(seconds=HOLD_EXPIRY_S + 1)
            )

    assert every_fault(faults, observer, setup, sweep) > 3


def test_tc_nfr3_proposal_execution_is_all_or_nothing(
    make_cafe: Callable[..., Cafe], faults: FaultInjector, observer: Engine
) -> None:
    def setup() -> tuple[Cafe, uuid.UUID]:
        cafe = make_cafe()
        return cafe, cafe.replenish_proposal()

    statements = every_fault(faults, observer, setup, lambda c: c[0].approve(c[1]))
    assert statements > 3


def test_the_injector_does_see_a_partial_write(
    make_cafe: Callable[..., Cafe], faults: FaultInjector, observer: Engine, engine: Engine
) -> None:
    """Control: an operation split over two transactions must fail the check.

    A portion is taken in one transaction and the order would be written in the next;
    a fault in the second leaves a portion allocated that no order holds.
    """

    def split_reserve(cafe: Cafe) -> None:
        with engine.begin() as connection:
            connection.execute(
                text("UPDATE daily_inventory SET allocated = allocated + 1 WHERE item_id = :i"),
                {"i": cafe.thali.id},
            )
        with engine.begin() as connection:
            connection.execute(text("SELECT 1"))

    with pytest.raises(AssertionError, match="after recovery"):
        every_fault(faults, observer, make_cafe, split_reserve)


def test_tc_nfr6_no_payment_call_with_a_transaction_open(
    make_cafe: Callable[..., Cafe], spy: NoTransactionSpy, engine: Engine
) -> None:
    cafe = make_cafe()
    first = cafe.placed()
    raised = cafe.modify(first, teas=3)
    assert raised.status_code == 200, raised.text
    lowered = cafe.modify(raised.json(), teas=0)
    assert lowered.status_code == 200, lowered.text
    assert cafe.cancel(lowered.json()).status_code == 200
    assert cafe.admin_cancel(cafe.placed()).status_code == 200
    declined = make_cafe(FakePaymentGateway(outcome=AuthOutcome.DECLINED))
    failed = declined.place()
    assert failed.status_code == 201 and failed.json()["status"] == "PAYMENT_FAILED"

    # The outbox, with a refund left PENDING while the gateway was down.
    down = make_cafe(FakePaymentGateway(unavailable=True))
    assert down.cancel(down.placed()).json()["refund"]["status"] == "PENDING"
    with Session(engine, expire_on_commit=False) as session:
        delivered = OutboxDeliverer(session, SpyGateway(FakePaymentGateway(), spy)).deliver()
    assert delivered >= 1

    kinds = {what for what, _ in spy.calls}
    assert kinds == {"authorise", "refund"}
    assert spy.violations == []


class SpyProvider:
    """An unreachable LLM that notes whether a transaction was open when it was called."""

    model = "spy"

    def __init__(self, spy: NoTransactionSpy) -> None:
        self.spy = spy

    def complete(self, request: LLMRequest) -> LLMResponse:
        self.spy.check("llm")
        raise LLMProviderError("offline")


def test_tc_nfr6_no_llm_call_with_a_transaction_open(
    make_cafe: Callable[..., Cafe], spy: NoTransactionSpy, engine: Engine
) -> None:
    make_cafe().placed()
    provider = SpyProvider(spy)
    with Session(engine, expire_on_commit=False) as session:

        def llm(s: Session) -> GuardedLLMClient:
            return GuardedLLMClient(
                provider, s, daily_cap=50, breaker=CircuitBreaker(), cache=ResponseCache()
            )

        service = AgentService(session, llm)
        service.request_run(AgentTrigger.ON_DEMAND, None, NOW)
        assert service.run_next(NOW) is not None
    assert [what for what, _ in spy.calls] and spy.violations == []
