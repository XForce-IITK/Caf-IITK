"""Menu-release rush load generator (NFR-1, NFR-2, NFR-13).

Fires N concurrent order requests for one item and one slot at a running
caf-api, then checks the responses and the database against the only correct
outcome: min(portions, seats) orders ACCEPTED, every other request 409, and the
counters equal to the number of accepted orders.

The tests drive it through the `live_stack` fixture. Against the Compose stack:

    cd backend
    CAF_JWT_SECRET=<the stack's secret> .venv/bin/python tests/loadgen.py \\
        --base-url http://localhost:8000 \\
        --database-url postgresql+psycopg://caf:caf@localhost:5432/caf

Repeat --base-url to alternate requests between several API processes.

With --mixed SECONDS it instead runs the NFR-4 workload: Students place, modify
and cancel orders at random across the processes for that long, after which no
response may be a server error and every counter must equal what the orders hold.

Each run seeds its own item, slot and Students and leaves them behind, so point
it at a development or test database only. P-MENU_OPEN is set to 00:00 for the
duration and restored afterwards, so the rush can run at any time of day.
"""

import argparse
import asyncio
import random
import sys
import time as timer
import uuid
from collections import Counter
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import time, timedelta
from typing import Any

import httpx
from sqlalchemy import Engine, create_engine, func, select, text, update
from sqlalchemy.orm import Session

from app.core import clock
from app.core.security import create_access_token
from app.models.capacity import DailyInventory, ServiceDay, Slot
from app.models.catalogue import MenuItem
from app.models.enums import (
    ItemCategory,
    ModificationStatus,
    OrderStatus,
    PaymentCause,
    PaymentKind,
    Role,
)
from app.models.identity import User
from app.models.ordering import Order, OrderLine, OrderModification, Payment
from app.models.platform import Setting

MENU_OPEN = "P-MENU_OPEN"


@dataclass(frozen=True)
class Scenario:
    item_id: uuid.UUID
    slot_id: uuid.UUID
    portions: int
    seats: int
    # One access token per Student; each Student sends one request.
    tokens: list[str]

    @property
    def expected_accepted(self) -> int:
        return min(self.portions, self.seats, len(self.tokens))


@dataclass
class RunReport:
    accepted: int = 0
    rejected: int = 0
    statuses: Counter[int] = field(default_factory=Counter)
    available_portions: int = 0
    remaining_seats: int = 0
    violations: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.violations

    def summary(self) -> str:
        verdict = "OK" if self.ok else "FAILED: " + "; ".join(self.violations)
        return (
            f"accepted={self.accepted} rejected={self.rejected} "
            f"portions_left={self.available_portions} seats_left={self.remaining_seats} "
            f"http={dict(sorted(self.statuses.items()))} {verdict}"
        )


@contextmanager
def menu_open_all_day(engine: Engine) -> Iterator[None]:
    with Session(engine) as session, session.begin():
        original = session.scalars(select(Setting.value).where(Setting.key == MENU_OPEN)).one()
        session.execute(update(Setting).where(Setting.key == MENU_OPEN).values(value="00:00"))
    try:
        yield
    finally:
        with Session(engine) as session, session.begin():
            session.execute(update(Setting).where(Setting.key == MENU_OPEN).values(value=original))


def seed(engine: Engine, *, requests: int, portions: int, seats: int) -> Scenario:
    """One item with `portions`, one slot with `seats`, and `requests` Students."""
    now = clock.now()
    today = now.date()
    item = MenuItem(
        id=uuid.uuid4(),
        name=f"Rush Thali {uuid.uuid4().hex[:8]}",
        category=ItemCategory.MEAL,
        price_paise=8000,
    )
    students = [
        User(
            id=uuid.uuid4(),
            name="Rush Student",
            email=f"rush-{uuid.uuid4().hex}@iitk.ac.in",
            password_hash="unused",
            role=Role.STUDENT,
        )
        for _ in range(requests)
    ]
    # Bookable whenever the run happens: it starts an hour from now, on today's service
    # date. `now` has microseconds, so the slot never collides with an earlier run's.
    slot = Slot(
        id=uuid.uuid4(),
        service_date=today,
        starts_at=now + timedelta(hours=1),
        ends_at=now + timedelta(hours=1, minutes=15),
        capacity=seats,
    )
    with Session(engine, expire_on_commit=False) as session, session.begin():
        if session.get(ServiceDay, today) is None:
            session.add(
                ServiceDay(
                    service_date=today,
                    window_start=time(0, 0),
                    window_end=time(23, 45),
                    slot_len_min=15,
                    default_capacity=30,
                )
            )
        session.add_all([item, *students])
        session.flush()
        session.add_all([slot, DailyInventory(item_id=item.id, service_date=today, total=portions)])
    return Scenario(
        item_id=item.id,
        slot_id=slot.id,
        portions=portions,
        seats=seats,
        tokens=[create_access_token(student.id, student.role) for student in students],
    )


async def fire(
    base_urls: Sequence[str], scenario: Scenario, *, timeout_s: float = 120
) -> list[httpx.Response]:
    """Quote once, then send every Student's order at the same time.

    Requests alternate between `base_urls`, so with one URL per API process every
    process is certain to take part in the race (NFR-13).
    """
    cart = {
        "slot_id": str(scenario.slot_id),
        "lines": [{"item_id": str(scenario.item_id), "qty": 1}],
    }
    limits = httpx.Limits(max_connections=len(scenario.tokens))
    async with httpx.AsyncClient(timeout=timeout_s, limits=limits) as client:
        quote = await client.post(
            f"{base_urls[0]}/api/v1/quotes",
            json=cart,
            headers={"Authorization": f"Bearer {scenario.tokens[0]}"},
        )
        quote.raise_for_status()
        body = cart | {"quoted_payable_paise": quote.json()["payable_paise"]}
        return await asyncio.gather(
            *(
                client.post(
                    f"{base_urls[number % len(base_urls)]}/api/v1/orders",
                    json=body,
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Idempotency-Key": uuid.uuid4().hex,
                    },
                )
                for number, token in enumerate(scenario.tokens)
            )
        )


def verify(engine: Engine, scenario: Scenario, responses: list[httpx.Response]) -> RunReport:
    report = RunReport(statuses=Counter(r.status_code for r in responses))
    for response in responses:
        if response.status_code == httpx.codes.CREATED and response.json()["status"] == "ACCEPTED":
            report.accepted += 1
        elif response.status_code == httpx.codes.CONFLICT:
            report.rejected += 1
        else:
            report.violations.append(
                f"unexpected response {response.status_code}: {response.text[:200]}"
            )

    with Session(engine) as session:
        stock = session.scalars(
            select(DailyInventory).where(DailyInventory.item_id == scenario.item_id)
        ).one()
        slot = session.scalars(select(Slot).where(Slot.id == scenario.slot_id)).one()
        by_status = {
            status: count
            for status, count in session.execute(
                select(Order.status, func.count())
                .where(Order.slot_id == scenario.slot_id)
                .group_by(Order.status)
            )
        }
    report.available_portions = stock.total - stock.allocated
    report.remaining_seats = slot.capacity - slot.booked

    expected = scenario.expected_accepted
    checks = {
        "accepted responses": (report.accepted, expected),
        "409 responses": (report.rejected, len(scenario.tokens) - expected),
        "ACCEPTED orders in the database": (by_status.get(OrderStatus.ACCEPTED, 0), expected),
        "orders in any other state": (
            sum(by_status.values()) - by_status.get(OrderStatus.ACCEPTED, 0),
            0,
        ),
        "portions allocated": (stock.allocated, expected),
        "seats booked": (slot.booked, expected),
    }
    report.violations += [
        f"{name}: {actual}, expected {wanted}"
        for name, (actual, wanted) in checks.items()
        if actual != wanted
    ]
    return report


def run_rush(
    base_urls: Sequence[str],
    engine: Engine,
    *,
    requests: int,
    portions: int,
    seats: int,
    runs: int,
) -> list[RunReport]:
    reports = []
    with menu_open_all_day(engine):
        for _ in range(runs):
            scenario = seed(engine, requests=requests, portions=portions, seats=seats)
            responses = asyncio.run(fire(base_urls, scenario))
            reports.append(verify(engine, scenario, responses))
    return reports


# --- US-30 AC3 and AC4: modify and cancel under concurrency (NFR-4, NFR-5) -----------

# Answers a correct server may give under contention; anything else is a failure.
HANDLED = frozenset({200, 201, 402, 409, 422})


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "Idempotency-Key": uuid.uuid4().hex}


def _cart(slot_id: uuid.UUID, lines: dict[uuid.UUID, int]) -> dict[str, Any]:
    return {
        "slot_id": str(slot_id),
        "lines": [{"item_id": str(item_id), "qty": qty} for item_id, qty in lines.items()],
    }


async def _place(
    client: httpx.AsyncClient, base_url: str, token: str, cart: dict[str, Any]
) -> httpx.Response:
    quote = await client.post(
        f"{base_url}/api/v1/quotes", json=cart, headers={"Authorization": f"Bearer {token}"}
    )
    if quote.status_code != httpx.codes.OK:
        return quote
    return await client.post(
        f"{base_url}/api/v1/orders",
        json=cart | {"quoted_payable_paise": quote.json()["payable_paise"]},
        headers=_auth(token),
    )


async def _quote_change(
    client: httpx.AsyncClient, base_url: str, token: str, order_id: str, cart: dict[str, Any]
) -> httpx.Response:
    return await client.post(
        f"{base_url}/api/v1/orders/{order_id}/quote",
        json=cart,
        headers={"Authorization": f"Bearer {token}"},
    )


async def _modify(
    client: httpx.AsyncClient,
    base_url: str,
    token: str,
    order: dict[str, Any],
    cart: dict[str, Any],
    payable: int,
) -> httpx.Response:
    return await client.patch(
        f"{base_url}/api/v1/orders/{order['id']}",
        json=cart | {"quoted_payable_paise": payable, "version": order["version"]},
        headers=_auth(token),
    )


async def _cancel(
    client: httpx.AsyncClient, base_url: str, token: str, order: dict[str, Any]
) -> httpx.Response:
    return await client.post(
        f"{base_url}/api/v1/orders/{order['id']}/cancel",
        json={"version": order["version"]},
        headers=_auth(token),
    )


@dataclass
class RaceReport:
    modify_won: int = 0
    cancel_won: int = 0
    violations: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.violations

    def summary(self) -> str:
        verdict = "OK" if self.ok else "FAILED: " + "; ".join(self.violations[:10])
        return f"modify won={self.modify_won} cancel won={self.cancel_won} {verdict}"


def race_modify_and_cancel(base_urls: Sequence[str], engine: Engine, *, orders: int) -> RaceReport:
    """NFR-5: a modify and a cancel at the same moment on each of `orders` ACCEPTED
    orders, sent to different processes. Exactly one of each pair may succeed.

    Even orders go from 1 portion to 2, so the modify is charged between two
    transactions; odd ones go from 2 to 1 and are applied, with a refund, in one.
    """
    with menu_open_all_day(engine):
        scenario = seed(engine, requests=orders, portions=4 * orders, seats=orders)
        return asyncio.run(_race(base_urls, engine, scenario))


async def _race(base_urls: Sequence[str], engine: Engine, scenario: Scenario) -> RaceReport:
    first, second = base_urls[0], base_urls[-1]
    start = [1 + number % 2 for number in range(len(scenario.tokens))]
    async with httpx.AsyncClient(timeout=120) as client:
        placed = await asyncio.gather(
            *(
                _place(client, first, token, _cart(scenario.slot_id, {scenario.item_id: qty}))
                for token, qty in zip(scenario.tokens, start, strict=True)
            )
        )
        if any(response.status_code != httpx.codes.CREATED for response in placed):
            raise RuntimeError(f"setup: placing gave {[r.status_code for r in placed]}")
        orders = [response.json() for response in placed]
        changes = [_cart(scenario.slot_id, {scenario.item_id: 3 - qty}) for qty in start]
        # Priced beforehand, so the race is between the two writes alone.
        quotes = await asyncio.gather(
            *(
                _quote_change(client, first, token, order["id"], change)
                for order, change, token in zip(orders, changes, scenario.tokens, strict=True)
            )
        )
        pairs = await asyncio.gather(
            *(
                asyncio.gather(
                    _modify(
                        client, first, token, order, change, quote.json()["quote"]["payable_paise"]
                    ),
                    _cancel(client, second, token, order),
                )
                for order, change, quote, token in zip(
                    orders, changes, quotes, scenario.tokens, strict=True
                )
            )
        )

    report = RaceReport()
    with Session(engine) as session:
        for number, (order, (modify, cancel)) in enumerate(zip(orders, pairs, strict=True)):
            row = session.get_one(Order, uuid.UUID(order["id"]))
            lines = list(session.scalars(select(OrderLine.qty).where(OrderLine.order_id == row.id)))
            refunds = list(
                session.scalars(
                    select(Payment.cause).where(
                        Payment.order_id == row.id, Payment.kind == PaymentKind.REFUND
                    )
                )
            )
            codes = (modify.status_code, cancel.status_code)
            if codes == (200, 409):
                report.modify_won += 1
                # Only a modification that lowered the price refunds anything.
                expected = [PaymentCause.MODIFY] if start[number] == 2 else []
                if (row.status, lines, refunds) != (
                    OrderStatus.ACCEPTED,
                    [3 - start[number]],
                    expected,
                ):
                    report.violations.append(
                        f"order {number}: modify won but {row.status}, lines {lines}, "
                        f"refunds {refunds}"
                    )
            elif codes == (409, 200):
                report.cancel_won += 1
                if (row.status, lines, refunds) != (
                    OrderStatus.CANCELLED,
                    [start[number]],
                    [PaymentCause.CANCEL],
                ):
                    report.violations.append(
                        f"order {number}: cancel won but {row.status}, lines {lines}, "
                        f"refunds {refunds}"
                    )
            else:
                report.violations.append(
                    f"order {number}: modify {codes[0]} and cancel {codes[1]}; "
                    "expected exactly one 200 and one 409"
                )
    report.violations += check_counters(engine)
    return report


@dataclass
class MixedReport:
    seconds: float = 0
    requests: Counter[str] = field(default_factory=Counter)
    # Detected by PostgreSQL and retried by the service (NFR-4); not failures in themselves.
    deadlocks_detected: int = 0
    violations: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.violations

    def summary(self) -> str:
        verdict = "OK" if self.ok else "FAILED: " + "; ".join(self.violations[:10])
        counts = " ".join(f"{key}={n}" for key, n in sorted(self.requests.items()))
        return (
            f"mixed {self.seconds:.0f}s: {sum(self.requests.values())} requests ({counts}) "
            f"deadlocks_detected={self.deadlocks_detected} {verdict}"
        )


def seed_mixed(
    engine: Engine, *, students: int
) -> tuple[list[uuid.UUID], list[uuid.UUID], list[str]]:
    """Three items and two slots, scarce enough that requests contend and some sell out."""
    now = clock.now()
    today = now.date()
    items = [
        MenuItem(
            id=uuid.uuid4(),
            name=f"Mixed {name} {uuid.uuid4().hex[:8]}",
            category=ItemCategory.MEAL,
            price_paise=price,
        )
        for name, price in [("Thali", 8000), ("Biryani", 12000), ("Dosa", 6000)]
    ]
    slots = [
        Slot(
            id=uuid.uuid4(),
            service_date=today,
            starts_at=now + timedelta(hours=1, minutes=15 * n),
            ends_at=now + timedelta(hours=1, minutes=15 * (n + 1)),
            capacity=students // 2,
        )
        for n in range(2)
    ]
    users = [
        User(
            id=uuid.uuid4(),
            name="Mixed Student",
            email=f"mixed-{uuid.uuid4().hex}@iitk.ac.in",
            password_hash="unused",
            role=Role.STUDENT,
        )
        for _ in range(students)
    ]
    with Session(engine, expire_on_commit=False) as session, session.begin():
        if session.get(ServiceDay, today) is None:
            session.add(
                ServiceDay(
                    service_date=today,
                    window_start=time(0, 0),
                    window_end=time(23, 45),
                    slot_len_min=15,
                    default_capacity=30,
                )
            )
        session.add_all([*items, *users])
        session.flush()
        session.add_all(slots)
        session.add_all(
            DailyInventory(item_id=item.id, service_date=today, total=students) for item in items
        )
    return (
        [item.id for item in items],
        [slot.id for slot in slots],
        [create_access_token(user.id, user.role) for user in users],
    )


def run_mixed(
    base_urls: Sequence[str], engine: Engine, *, seconds: float, students: int = 40
) -> MixedReport:
    """NFR-4: each Student places, modifies and cancels at random across the processes
    for `seconds`. No answer may be a server error (an unhandled deadlock shows as a
    500, one still failing after the service's retries as a 503), and afterwards every
    counter must equal what the orders hold.
    """
    with menu_open_all_day(engine):
        items, slots, tokens = seed_mixed(engine, students=students)
        deadlocks_before = _deadlocks(engine)
        report = asyncio.run(_mixed(base_urls, items, slots, tokens, seconds))
        report.deadlocks_detected = _deadlocks(engine) - deadlocks_before
    report.violations += check_counters(engine)
    return report


async def _mixed(
    base_urls: Sequence[str],
    items: list[uuid.UUID],
    slots: list[uuid.UUID],
    tokens: list[str],
    seconds: float,
) -> MixedReport:
    report = MixedReport(seconds=seconds)
    rng = random.Random()
    deadline = timer.monotonic() + seconds

    def random_cart() -> dict[str, Any]:
        chosen = rng.sample(items, rng.randint(1, 2))
        return _cart(rng.choice(slots), {item_id: rng.randint(1, 3) for item_id in chosen})

    async def act(
        client: httpx.AsyncClient, token: str, mine: list[dict[str, Any]]
    ) -> tuple[str, httpx.Response]:
        base_url = rng.choice(base_urls)
        action = rng.choice(["place", "modify", "modify", "cancel"]) if mine else "place"
        if action == "place":
            return action, await _place(client, base_url, token, random_cart())
        order = rng.choice(mine)
        if action == "cancel":
            return action, await _cancel(client, base_url, token, order)
        cart = random_cart()
        quote = await _quote_change(client, base_url, token, order["id"], cart)
        if quote.status_code != httpx.codes.OK:
            return "quote", quote
        payable = quote.json()["quote"]["payable_paise"]
        return action, await _modify(client, base_url, token, order, cart, payable)

    async def student(client: httpx.AsyncClient, token: str) -> None:
        mine: list[dict[str, Any]] = []
        while timer.monotonic() < deadline:
            action, response = await act(client, token, mine)
            report.requests[f"{action}:{response.status_code}"] += 1
            if response.status_code not in HANDLED:
                report.violations.append(
                    f"{action} gave {response.status_code}: {response.text[:200]}"
                )
            if response.status_code in (httpx.codes.OK, httpx.codes.CREATED):
                body = response.json()
                mine = [order for order in mine if order["id"] != body["id"]]
                if body["status"] == "ACCEPTED":
                    mine.append(body)
            elif response.status_code == httpx.codes.CONFLICT and mine:
                # A stale version or state: reload this Student's orders and carry on.
                mine = await _reload(client, rng.choice(base_urls), token, mine)

    limits = httpx.Limits(max_connections=len(tokens))
    async with httpx.AsyncClient(timeout=120, limits=limits) as client:
        await asyncio.gather(*(student(client, token) for token in tokens))
    return report


async def _reload(
    client: httpx.AsyncClient, base_url: str, token: str, orders: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    fresh = await asyncio.gather(
        *(
            client.get(
                f"{base_url}/api/v1/orders/{order['id']}",
                headers={"Authorization": f"Bearer {token}"},
            )
            for order in orders
        )
    )
    return [
        r.json()
        for r in fresh
        if r.status_code == httpx.codes.OK and r.json()["status"] == "ACCEPTED"
    ]


def _deadlocks(engine: Engine) -> int:
    with engine.connect() as connection:
        return int(
            connection.execute(
                text("SELECT deadlocks FROM pg_stat_database WHERE datname = current_database()")
            ).scalar_one()
        )


# Order states that still hold their portions and seat (Table 4.6-A).
_HOLDING = (
    OrderStatus.PENDING_PAYMENT,
    OrderStatus.ACCEPTED,
    OrderStatus.PREPARING,
    OrderStatus.READY,
)


def check_counters(engine: Engine) -> list[str]:
    """Every counter equals what the orders hold, no modification is left holding, and
    every cancelled order has exactly one refund (NFR-1, FR-36, FR-39)."""
    violations = []
    with Session(engine) as session:
        held_portions = {
            item_id: int(qty)
            for item_id, qty in session.execute(
                select(OrderLine.item_id, func.sum(OrderLine.qty))
                .join(Order, Order.id == OrderLine.order_id)
                .where(Order.status.in_(_HOLDING))
                .group_by(OrderLine.item_id)
            )
        }
        for stock in session.scalars(select(DailyInventory)):
            held = held_portions.get(stock.item_id, 0)
            if stock.allocated != held:
                violations.append(f"item {stock.item_id}: allocated {stock.allocated}, held {held}")
        held_seats = {
            slot_id: count
            for slot_id, count in session.execute(
                select(Order.slot_id, func.count())
                .where(Order.status.in_(_HOLDING))
                .group_by(Order.slot_id)
            )
        }
        for slot in session.scalars(select(Slot)):
            held = held_seats.get(slot.id, 0)
            if slot.booked != held:
                violations.append(f"slot {slot.id}: booked {slot.booked}, held {held}")
        holding = session.scalar(
            select(func.count())
            .select_from(OrderModification)
            .where(OrderModification.status == ModificationStatus.HOLDING)
        )
        if holding:
            violations.append(f"{holding} modifications still HOLDING")
        refunds = (
            select(func.count())
            .select_from(Payment)
            .where(
                Payment.order_id == Order.id,
                Payment.kind == PaymentKind.REFUND,
                Payment.cause == PaymentCause.CANCEL,
            )
            .scalar_subquery()
        )
        wrong = session.scalar(
            select(func.count())
            .select_from(Order)
            .where(Order.status == OrderStatus.CANCELLED, refunds != 1)
        )
        if wrong:
            violations.append(f"{wrong} cancelled orders without exactly one refund")
    return violations


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    parser.add_argument(
        "--base-url",
        action="append",
        help="caf-api URL; repeat to alternate between several (default http://localhost:8000)",
    )
    parser.add_argument("--database-url", required=True)
    # The NFR-1 acceptance figures.
    parser.add_argument("--requests", type=int, default=200)
    parser.add_argument("--portions", type=int, default=50)
    parser.add_argument("--seats", type=int, default=30)
    parser.add_argument("--runs", type=int, default=10)
    parser.add_argument(
        "--mixed",
        type=float,
        metavar="SECONDS",
        help="run the NFR-4 mixed create/modify/cancel workload for this long instead",
    )
    args = parser.parse_args(argv)
    base_urls = args.base_url or ["http://localhost:8000"]

    engine = create_engine(args.database_url)
    if args.mixed is not None:
        try:
            mixed = run_mixed(base_urls, engine, seconds=args.mixed)
        finally:
            engine.dispose()
        print(mixed.summary())
        return 0 if mixed.ok else 1
    try:
        reports = run_rush(
            base_urls,
            engine,
            requests=args.requests,
            portions=args.portions,
            seats=args.seats,
            runs=args.runs,
        )
    finally:
        engine.dispose()
    for number, report in enumerate(reports, start=1):
        print(f"run {number}: {report.summary()}")
    return 0 if all(report.ok for report in reports) else 1


if __name__ == "__main__":
    sys.exit(main())
