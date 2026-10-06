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

Each run seeds its own item, slot and Students and leaves them behind, so point
it at a development or test database only. P-MENU_OPEN is set to 00:00 for the
duration and restored afterwards, so the rush can run at any time of day.
"""

import argparse
import asyncio
import sys
import uuid
from collections import Counter
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import time, timedelta

import httpx
from sqlalchemy import Engine, create_engine, func, select, update
from sqlalchemy.orm import Session

from app.core import clock
from app.core.security import create_access_token
from app.models.capacity import DailyInventory, ServiceDay, Slot
from app.models.catalogue import MenuItem
from app.models.enums import ItemCategory, OrderStatus, Role
from app.models.identity import User
from app.models.ordering import Order
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
    args = parser.parse_args(argv)

    engine = create_engine(args.database_url)
    try:
        reports = run_rush(
            args.base_url or ["http://localhost:8000"],
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
