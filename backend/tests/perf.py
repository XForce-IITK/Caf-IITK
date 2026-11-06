"""Client-side performance measurement against a running caf-api (NFR-8 - NFR-12).

Each workload seeds its own Students, items and slots, sends real HTTP, and records
the latency of every request as the client sees it (connection, queueing and server
time together). Before and after each workload it also scrapes caf-api's /metrics, for
the server's own view: time per route and time waiting for row locks. Against the
Compose stack, from a container on its network (on Docker Desktop, the port proxy
from the host into the VM drops a few connections under this load):

    docker run --rm --network caf-iitk_default -e CAF_JWT_SECRET=<the stack's secret> \\
        -e PYTHONPATH=/srv:/srv/tests -v "$PWD/backend/tests:/srv/tests:ro" \\
        --entrypoint python caf-iitk-api /srv/tests/perf.py --fresh \\
        --base-url http://api:8000 --mockpay-url http://mockpay:8001 \\
        --database-url postgresql+psycopg://caf:caf@db:5432/caf

mockpay is set to approve at once, so order latency excludes any mock-payment delay
(NFR-8). Like loadgen.py, it leaves its rows behind and sets P-MENU_OPEN to 00:00
while it runs, and --fresh empties the database: point it at a development or test
database only.
"""

import argparse
import asyncio
import json
import random
import sys
import time as timer
import uuid
from collections import Counter
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import asdict, dataclass, field
from datetime import time, timedelta
from typing import Any

import httpx
from loadgen import menu_open_all_day, seed
from prometheus_client.parser import text_string_to_metric_families
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session

from app.core import clock
from app.core.config import get_settings
from app.core.security import create_access_token
from app.models.capacity import DailyInventory, ServiceDay, Slot
from app.models.catalogue import MenuItem
from app.models.enums import AgentRunStatus, AgentTrigger, ItemCategory, Role
from app.models.identity import User
from app.modules.agent.client import get_llm_client
from app.modules.agent.service import AgentService

# Answers that are the system working as designed, not errors (NFR-10).
REJECTIONS = frozenset({409, 422})
# NFR-9: what a Student and the kitchen screen read.
READS = ("menu", "slots", "history", "kitchen")


@dataclass
class Latencies:
    """Every request's latency in milliseconds, and its status."""

    samples: list[float] = field(default_factory=list)
    statuses: Counter[int] = field(default_factory=Counter)
    # Status 599: no response at all, counted here by what the client raised.
    no_response: Counter[str] = field(default_factory=Counter)

    def add(self, ms: float, status: int) -> None:
        self.samples.append(ms)
        self.statuses[status] += 1

    def percentile(self, p: float) -> float:
        """Nearest-rank percentile; 0 with no samples."""
        if not self.samples:
            return 0.0
        ordered = sorted(self.samples)
        rank = max(1, -(-len(ordered) * p // 100))  # ceil(n * p / 100)
        return ordered[int(rank) - 1]

    @property
    def errors(self) -> int:
        """Responses that are neither a success nor a designed rejection."""
        return sum(
            n for status, n in self.statuses.items() if status >= 300 and status not in REJECTIONS
        )

    def row(self) -> dict[str, Any]:
        row = {
            "requests": len(self.samples),
            "p50_ms": round(self.percentile(50), 1),
            "p95_ms": round(self.percentile(95), 1),
            "p99_ms": round(self.percentile(99), 1),
            "max_ms": round(max(self.samples, default=0.0), 1),
            "errors": self.errors,
            "statuses": dict(sorted(self.statuses.items())),
        }
        if self.no_response:
            row["no_response"] = dict(self.no_response)
        return row


@dataclass
class Result:
    workload: str
    target: str
    met: bool | None  # None: not measured
    figures: dict[str, Any]


@dataclass
class Run:
    """One workload: its results against the NFRs and what /metrics saw meanwhile."""

    workload: str
    results: list[Result]
    server: dict[str, dict[str, Any]]


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _timed(latencies: Latencies, request: Awaitable[httpx.Response]) -> httpx.Response | None:
    """Await `request`, which has not started yet, and record how long it took."""
    started = timer.perf_counter()
    try:
        response = await request
    except httpx.HTTPError as exc:
        latencies.add((timer.perf_counter() - started) * 1000, 599)
        latencies.no_response[type(exc).__name__] += 1
        return None
    latencies.add((timer.perf_counter() - started) * 1000, response.status_code)
    return response


async def _quote(client: httpx.AsyncClient, base_url: str, token: str, cart: dict[str, Any]) -> int:
    response = await client.post(f"{base_url}/api/v1/quotes", json=cart, headers=_bearer(token))
    response.raise_for_status()
    payable: int = response.json()["payable_paise"]
    return payable


async def _order(
    client: httpx.AsyncClient,
    base_url: str,
    token: str,
    cart: dict[str, Any],
    payable: int,
    latencies: Latencies,
) -> httpx.Response | None:
    """Time POST /orders only; the quote before it is the Student's earlier step."""
    headers = _bearer(token) | {"Idempotency-Key": uuid.uuid4().hex}
    body = cart | {"quoted_payable_paise": payable}
    return await _timed(
        latencies, client.post(f"{base_url}/api/v1/orders", json=body, headers=headers)
    )


def _limits(clients: int) -> httpx.Limits:
    return httpx.Limits(max_connections=clients, max_keepalive_connections=clients)


async def _drain(jobs: Sequence[Callable[[], Awaitable[object]]], clients: int) -> None:
    """Run `jobs` with at most `clients` in flight, as that many concurrent users would."""
    queue = list(reversed(jobs))

    async def worker() -> None:
        while queue:
            await queue.pop()()

    await asyncio.gather(*(worker() for _ in range(clients)))


# --- NFR-8: order creation, 50 clients on one item and one slot -------------------------


async def _same_item_and_slot(
    base_url: str, tokens: list[str], cart: dict[str, Any], clients: int
) -> Latencies:
    latencies = Latencies()
    async with httpx.AsyncClient(timeout=60, limits=_limits(clients)) as client:
        payable = await _quote(client, base_url, tokens[0], cart)

        def job(token: str) -> Callable[[], Awaitable[object]]:
            return lambda: _order(client, base_url, token, cart, payable, latencies)

        await _drain([job(t) for t in tokens], clients)
    return latencies


def nfr8(base_url: str, engine: Engine, *, clients: int = 50, orders: int = 200) -> Result:
    # Enough portions and seats for every order, so each one is a full creation.
    scenario = seed(engine, requests=orders, portions=orders, seats=orders)
    cart = {
        "slot_id": str(scenario.slot_id),
        "lines": [{"item_id": str(scenario.item_id), "qty": 1}],
    }
    latencies = asyncio.run(_same_item_and_slot(base_url, scenario.tokens, cart, clients))
    row = latencies.row()
    met = row["p95_ms"] <= 500 and row["p99_ms"] <= 1000 and latencies.errors == 0
    return Result(
        f"NFR-8: {clients} clients, {orders} orders, one item and slot",
        "p95 ≤ 500 ms, p99 ≤ 1 s",
        met,
        row,
    )


# --- The design workload (NFR-12), also used for the reads of NFR-9 ---------------------


@dataclass(frozen=True)
class DesignDay:
    student_tokens: list[str]
    kitchen_token: str
    item_ids: list[uuid.UUID]
    slot_ids: list[uuid.UUID]


def seed_design(
    engine: Engine,
    *,
    students: int = 500,
    items: int = 15,
    slots: int = 10,
    seats: int = 30,
    portions: int = 100,
) -> DesignDay:
    """NFR-12: 500 Students, about 15 items and 10 slots of 30 seats, all bookable today."""
    now = clock.now()
    today = now.date()
    suffix = uuid.uuid4().hex[:8]
    users = [
        User(
            id=uuid.uuid4(),
            name="Perf Student",
            email=f"perf-{uuid.uuid4().hex}@iitk.ac.in",
            password_hash="unused",
            role=Role.STUDENT,
        )
        for _ in range(students)
    ]
    kitchen = User(
        id=uuid.uuid4(),
        name="Perf Kitchen",
        email=f"perf-kitchen-{suffix}@iitk.ac.in",
        password_hash="unused",
        role=Role.KITCHEN,
    )
    menu = [
        MenuItem(
            id=uuid.uuid4(),
            name=f"Perf item {n} {suffix}",
            category=ItemCategory.MEAL if n % 3 else ItemCategory.BEVERAGE,
            price_paise=2000 + 500 * n,
        )
        for n in range(items)
    ]
    # The first slot starts soon, so the kitchen queue (current and next slot) has orders.
    day_slots = [
        Slot(
            id=uuid.uuid4(),
            service_date=today,
            starts_at=now + timedelta(minutes=30 + 15 * n),
            ends_at=now + timedelta(minutes=45 + 15 * n),
            capacity=seats,
        )
        for n in range(slots)
    ]
    with Session(engine, expire_on_commit=False) as session, session.begin():
        if session.get(ServiceDay, today) is None:
            session.add(
                ServiceDay(
                    service_date=today,
                    window_start=time(0, 0),
                    window_end=time(23, 45),
                    slot_len_min=15,
                    # The seeded slots carry their own capacity; this is the design's,
                    # within the 1-100 a day allows (NFR-10's slots hold 400).
                    default_capacity=30,
                )
            )
        session.add_all([*users, kitchen, *menu])
        session.flush()
        session.add_all(day_slots)
        session.add_all(
            DailyInventory(item_id=item.id, service_date=today, total=portions) for item in menu
        )
    return DesignDay(
        student_tokens=[create_access_token(u.id, u.role) for u in users],
        kitchen_token=create_access_token(kitchen.id, kitchen.role),
        item_ids=[item.id for item in menu],
        slot_ids=[slot.id for slot in day_slots],
    )


async def _readers(
    base_url: str, day: DesignDay, users: int, until: Callable[[], bool], rng: random.Random
) -> dict[str, Latencies]:
    """`users` concurrent readers, each sending one read after another until `until()`."""
    by_read = {read: Latencies() for read in READS}
    paths = {
        "menu": "/api/v1/menu",
        "slots": "/api/v1/slots",
        "history": "/api/v1/orders",
        "kitchen": "/api/v1/kitchen/queue",
    }
    async with httpx.AsyncClient(timeout=60, limits=_limits(users)) as client:

        async def reader(n: int) -> None:
            student = day.student_tokens[n % len(day.student_tokens)]
            while not until():
                read = rng.choice(READS)
                token = day.kitchen_token if read == "kitchen" else student
                url = f"{base_url}{paths[read]}"
                await _timed(by_read[read], client.get(url, headers=_bearer(token)))

        await asyncio.gather(*(reader(n) for n in range(users)))
    return by_read


def _read_results(name: str, by_read: dict[str, Latencies]) -> list[Result]:
    results = []
    for read, latencies in by_read.items():
        row = latencies.row()
        results.append(
            Result(
                f"{name}: {read}",
                "p95 ≤ 200 ms",
                row["p95_ms"] <= 200 and latencies.errors == 0,
                row,
            )
        )
    return results


def nfr9(base_url: str, engine: Engine, *, users: int = 100, seconds: float = 30) -> list[Result]:
    day = seed_design(engine)
    deadline = timer.monotonic() + seconds
    by_read = asyncio.run(
        _readers(base_url, day, users, lambda: timer.monotonic() >= deadline, random.Random(9))
    )
    return _read_results(f"NFR-9: {users} readers for {seconds:.0f} s", by_read)


# --- NFR-10: 20 order creations per second for 60 s -------------------------------------


async def _open_loop(
    base_url: str, tokens: list[str], carts: list[dict[str, Any]], rate: float
) -> tuple[Latencies, float, float]:
    """Send one order every 1/rate s whatever the responses, as arrivals would come."""
    latencies = Latencies()
    lags: list[float] = []
    async with httpx.AsyncClient(timeout=60, limits=_limits(200)) as client:
        payables: dict[str, int] = {}
        for cart in carts:
            key = json.dumps(cart, sort_keys=True)
            if key not in payables:
                payables[key] = await _quote(client, base_url, tokens[0], cart)
        start = timer.monotonic()

        async def arrive(n: int, token: str, cart: dict[str, Any]) -> None:
            await asyncio.sleep(max(0.0, start + n / rate - timer.monotonic()))
            lags.append(timer.monotonic() - (start + n / rate))
            payable = payables[json.dumps(cart, sort_keys=True)]
            await _order(client, base_url, token, cart, payable, latencies)

        await asyncio.gather(
            *(arrive(n, t, c) for n, (t, c) in enumerate(zip(tokens, carts, strict=True)))
        )
        elapsed = timer.monotonic() - start
    return latencies, elapsed, max(lags, default=0.0)


def nfr10(base_url: str, engine: Engine, *, rate: float = 20, seconds: float = 60) -> Result:
    orders = int(rate * seconds)
    # An item has at most 500 portions a day (ck_daily_inventory_total_range), so the
    # orders go round-robin over enough items and slots for every one to be accepted.
    spread = -(-orders // 400)
    each = -(-orders // spread)
    day = seed_design(
        engine, students=orders, items=spread, slots=spread, seats=each, portions=each
    )
    carts = [
        {
            "slot_id": str(day.slot_ids[n % spread]),
            "lines": [{"item_id": str(day.item_ids[n % spread]), "qty": 1}],
        }
        for n in range(orders)
    ]
    latencies, elapsed, lag = asyncio.run(_open_loop(base_url, day.student_tokens, carts, rate))
    row = latencies.row()
    error_rate = latencies.errors / max(1, len(latencies.samples))
    row |= {
        "achieved_per_s": round(latencies.statuses[201] / elapsed, 1),
        "error_rate_pct": round(100 * error_rate, 2),
        "max_send_lag_ms": round(lag * 1000, 1),
    }
    return Result(
        f"NFR-10: {rate:g}/s for {seconds:.0f} s", "error rate < 1 %", error_rate < 0.01, row
    )


# --- NFR-12: the menu-release burst on the design workload, with readers alongside -------


async def _burst_with_readers(
    base_url: str, day: DesignDay, attempts: int, clients: int, readers: int, rng: random.Random
) -> tuple[Latencies, dict[str, Latencies], float]:
    orders = Latencies()
    done = asyncio.Event()
    students = rng.sample(day.student_tokens, attempts)
    async with httpx.AsyncClient(timeout=60, limits=_limits(clients)) as client:

        def job(token: str) -> Callable[[], Awaitable[object]]:
            items = rng.sample(day.item_ids, rng.randint(1, 2))
            cart = {
                "slot_id": str(rng.choice(day.slot_ids)),
                "lines": [{"item_id": str(item), "qty": 1} for item in items],
            }

            async def attempt() -> None:
                payable = await _quote(client, base_url, token, cart)
                await _order(client, base_url, token, cart, payable, orders)

            return attempt

        async def burst() -> float:
            started = timer.monotonic()
            await _drain([job(t) for t in students], clients)
            done.set()
            return timer.monotonic() - started

        elapsed, by_read = await asyncio.gather(
            burst(), _readers(base_url, day, readers, done.is_set, rng)
        )
    return orders, by_read, elapsed


def nfr12(
    base_url: str, engine: Engine, *, attempts: int = 200, clients: int = 50, readers: int = 100
) -> list[Result]:
    day = seed_design(engine)
    orders, by_read, elapsed = asyncio.run(
        _burst_with_readers(base_url, day, attempts, clients, readers, random.Random(12))
    )
    row = orders.row() | {"burst_s": round(elapsed, 1)}
    met = row["p95_ms"] <= 500 and row["p99_ms"] <= 1000 and orders.errors == 0 and elapsed <= 60
    name = f"NFR-12: {attempts} orders by {clients} clients + {readers} readers, design day"
    return [
        Result(f"{name}: orders", "p95 ≤ 500 ms, p99 ≤ 1 s; burst within 60 s", met, row),
        *_read_results(f"{name}: reads", by_read),
    ]


# --- NFR-11: one planning run, timed as caf-worker executes it -------------------------


def nfr11(engine: Engine) -> list[Result]:
    """Time AgentService.run_next, which is what caf-worker runs, without its poll wait."""
    with Session(engine, expire_on_commit=False) as session:
        service = AgentService(session, get_llm_client)
        now = clock.now()
        service.request_run(AgentTrigger.ON_DEMAND, None, now)
        started = timer.perf_counter()
        status = service.run_next(now)
        seconds = timer.perf_counter() - started
    llm = get_settings().llm_api_key is not None
    figures = {"status": status.value if status else None, "seconds": round(seconds, 2)}
    ran = status is AgentRunStatus.SUCCEEDED
    measured = Result(
        f"NFR-11: agent run, {'LLM' if llm else 'heuristic (no LLM key)'}",
        "≤ 60 s" if llm else "≤ 5 s",
        ran and seconds <= (60 if llm else 5),
        figures,
    )
    if llm:
        return [measured]
    return [
        measured,
        Result("NFR-11: agent run, LLM", "≤ 60 s", None, {"note": "no CAF_LLM_API_KEY set"}),
    ]


# --- The server's view, from /metrics ----------------------------------------------------

Samples = dict[tuple[str, frozenset[tuple[str, str]]], float]
_HISTOGRAMS = {
    "caf_http_request_duration_seconds": ("method", "route"),
    "caf_db_lock_wait_seconds": ("table",),
}


def scrape(base_url: str) -> Samples:
    """Every sample of the histograms above; empty if caf-api serves no /metrics."""
    response = httpx.get(f"{base_url}/metrics", timeout=30)
    if response.status_code != 200:
        return {}
    samples: Samples = {}
    for family in text_string_to_metric_families(response.text):
        if family.name in _HISTOGRAMS:
            for sample in family.samples:
                samples[(sample.name, frozenset(sample.labels.items()))] = sample.value
    return samples


def _bucket_p95(buckets: dict[float, float], count: float) -> str:
    """The upper bound of the bucket that holds the 95th percentile."""
    for bound, cumulative in sorted(buckets.items()):
        if cumulative >= 0.95 * count:
            return "> 10 s" if bound == float("inf") else f"≤ {bound * 1000:g} ms"
    return "—"


def server_view(before: Samples, after: Samples) -> dict[str, dict[str, Any]]:
    """What the server recorded between two scrapes, by route and by locked table.

    Histogram buckets are coarse, so p95 is a bucket bound, not an exact figure.
    """
    grouped: dict[str, dict[str, Any]] = {}
    for (name, labels), value in after.items():
        delta = value - before.get((name, labels), 0.0)
        if delta <= 0:
            continue
        family = next(f for f in _HISTOGRAMS if name.startswith(f))
        label = dict(labels)
        key = " ".join(label[k] for k in _HISTOGRAMS[family])
        if family == "caf_db_lock_wait_seconds":
            key = f"lock wait: {key}"
        group = grouped.setdefault(key, {"count": 0.0, "sum": 0.0, "buckets": Counter()})
        if name.endswith("_count"):
            group["count"] += delta
        elif name.endswith("_sum"):
            group["sum"] += delta
        elif name.endswith("_bucket"):  # summed over statuses
            group["buckets"][float(label["le"])] += delta
    return {
        key: {
            "count": int(g["count"]),
            "mean_ms": round(1000 * g["sum"] / g["count"], 1),
            "p95": _bucket_p95(g["buckets"], g["count"]),
        }
        for key, g in sorted(grouped.items())
        if g["count"] > 0
    }


# --- Running and reporting ---------------------------------------------------------------

WORKLOADS = ("nfr8", "nfr9", "nfr10", "nfr11", "nfr12")


def empty_database(engine: Engine) -> None:
    """Delete every row but the users, the settings and the schema version.

    Each workload's orders stay ACCEPTED, and the kitchen queue lists every open order
    of the next two slots and of any slot that has ended. Without this, NFR-12's
    kitchen reads would carry NFR-10's 1,200 orders, far more than a 30-seat slot holds.
    """
    with engine.begin() as connection:
        tables = connection.execute(
            text(
                "SELECT tablename FROM pg_tables WHERE schemaname = 'public' "
                "AND tablename NOT IN ('alembic_version', 'settings', 'users')"
            )
        ).scalars()
        connection.execute(text(f"TRUNCATE {', '.join(f'"{t}"' for t in tables)} CASCADE"))


def run(
    workloads: Sequence[str],
    base_url: str,
    mockpay_url: str,
    engine: Engine,
    *,
    scale: float = 1.0,
    fresh: bool = False,
    on_done: Callable[[Run], None] = lambda run: None,
) -> list[Run]:
    """Run each workload in turn; `scale` shrinks the sizes and durations (1.0 = the NFRs).

    With `fresh`, each workload starts from an empty database (`empty_database`).
    `on_done` sees each workload as it finishes, so a later crash loses nothing.
    """

    def n(value: float) -> int:
        return max(1, round(value * scale))

    # NFR-8 measures order creation without the mock-payment delay.
    httpx.put(
        f"{mockpay_url}/_control/outcome", json={"mode": "approve", "delay_ms": 0}
    ).raise_for_status()
    runs: list[Run] = []
    with menu_open_all_day(engine):
        for workload in workloads:
            if fresh:
                empty_database(engine)
            before = scrape(base_url)
            if workload == "nfr8":
                results = [nfr8(base_url, engine, clients=n(50), orders=n(200))]
            elif workload == "nfr9":
                results = nfr9(base_url, engine, users=n(100), seconds=30 * scale)
            elif workload == "nfr10":
                results = [nfr10(base_url, engine, rate=20, seconds=60 * scale)]
            elif workload == "nfr11":
                results = nfr11(engine)
            elif workload == "nfr12":
                results = nfr12(base_url, engine, attempts=n(200), clients=n(50), readers=n(100))
            # A scrape is itself a request, recorded once it has been answered, so it
            # falls in the next workload's window as a GET /metrics row, not in this one.
            runs.append(Run(workload, results, server_view(before, scrape(base_url))))
            on_done(runs[-1])
    return runs


def markdown(runs: Sequence[Run]) -> str:
    """The client-side table against each target, then the server's view per workload."""
    results = [r for run in runs for r in run.results]
    lines = [
        "| Workload | Target | Requests | p50 ms | p95 ms | p99 ms | Errors | Other | Met |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in results:
        f = r.figures
        other = {
            k: v
            for k, v in f.items()
            if k not in {"requests", "p50_ms", "p95_ms", "p99_ms", "errors"}
        }
        met = "—" if r.met is None else ("yes" if r.met else "**no**")
        lines.append(
            f"| {r.workload} | {r.target} | {f.get('requests', '')} | {f.get('p50_ms', '')} "
            f"| {f.get('p95_ms', '')} | {f.get('p99_ms', '')} | {f.get('errors', '')} "
            f"| {json.dumps(other)} | {met} |"
        )
    for run in runs:
        if not run.server:
            continue
        lines += [
            "",
            f"Server side during {run.workload} (from /metrics):",
            "",
            "| Route or lock | Count | Mean ms | p95 (bucket) |",
            "|---|---|---|---|",
        ]
        lines += [
            f"| {key} | {v['count']} | {v['mean_ms']} | {v['p95']} |"
            for key, v in run.server.items()
        ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--mockpay-url", default="http://localhost:8001")
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--workload", action="append", choices=WORKLOADS, help="default: all")
    parser.add_argument("--scale", type=float, default=1.0, help="shrink sizes and durations")
    parser.add_argument("--json", metavar="FILE", help="also write the results as JSON")
    parser.add_argument(
        "--fresh",
        action="store_true",
        help="empty every table but users and settings before each workload (local only)",
    )
    args = parser.parse_args(argv)

    for stream in (sys.stdout, sys.stderr):  # "≤" on a Windows console
        stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    done: list[Run] = []

    def finished(run: Run) -> None:
        done.append(run)
        print(markdown([run]), end="\n\n", file=sys.stderr, flush=True)
        if args.json:
            with open(args.json, "w", encoding="utf-8") as out:
                json.dump([asdict(r) for r in done], out, indent=2, ensure_ascii=False)

    engine = create_engine(args.database_url)
    try:
        runs = run(
            args.workload or WORKLOADS,
            args.base_url,
            args.mockpay_url,
            engine,
            scale=args.scale,
            fresh=args.fresh,
            on_done=finished,
        )
    finally:
        engine.dispose()
    print(markdown(runs))
    return 0 if all(r.met is not False for run in runs for r in run.results) else 1


if __name__ == "__main__":
    sys.exit(main())
