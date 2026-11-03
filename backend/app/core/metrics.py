"""Prometheus metrics served at GET /metrics (NFR-31, SADD 6.4).

caf-api runs several gunicorn processes, each counting its own requests. When
PROMETHEUS_MULTIPROC_DIR is set (gunicorn.conf.py sets it), every process writes
its samples there and /metrics adds them up, whichever process answers the scrape.

Agent runs execute in caf-worker, which serves no HTTP, so they are counted from
the agent_runs table at scrape time instead of in process memory.
"""

import os
import re
import time
from collections.abc import Callable, Iterable
from functools import wraps
from typing import Any, ParamSpec, Protocol, TypeVar

from fastapi.routing import iter_route_contexts
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    REGISTRY,
    CollectorRegistry,
    Counter,
    Histogram,
    generate_latest,
    multiprocess,
)
from prometheus_client.core import CounterMetricFamily, GaugeMetricFamily, Metric
from prometheus_client.registry import Collector
from sqlalchemy import Engine, event
from starlette.types import ASGIApp, Message, Receive, Scope, Send

__all__ = ["CONTENT_TYPE_LATEST", "MetricsMiddleware", "counts_order_outcome", "render"]

# A request that matched no route is labelled with this, not its path, so that
# probing random URLs cannot create an unbounded number of series.
UNMATCHED_ROUTE = "<unmatched>"

REQUEST_DURATION = Histogram(
    "caf_http_request_duration_seconds",
    "Time to answer a request, by route template; the _count series is the request rate.",
    ["method", "route", "status"],
)
ORDER_OUTCOMES = Counter(
    "caf_order_outcomes",
    "Order operations by result: the order's status on success, else the error.",
    ["operation", "outcome"],
)
LOCK_WAIT = Histogram(
    "caf_db_lock_wait_seconds",
    "Time spent in SELECT ... FOR UPDATE statements, by the table locked.",
    ["table"],
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
)


class MetricsMiddleware:
    """Times every HTTP request and labels it with the route template that served it."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self._templates: dict[int, str] | None = None

    def _template(self, scope: Scope) -> str:
        route = scope.get("route")
        if route is None:
            return UNMATCHED_ROUTE
        if self._templates is None:
            # The router stores the route as declared in its module router, without the
            # /api/v1 prefix; the app's route contexts know the full path.
            self._templates = {
                id(context.original_route): context.path_format
                for context in iter_route_contexts(scope["app"].routes)
                if context.path_format
            }
        return self._templates.get(id(route), getattr(route, "path", UNMATCHED_ROUTE))

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        started = time.perf_counter()
        status = 500

        async def send_wrapper(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            REQUEST_DURATION.labels(scope["method"], self._template(scope), str(status)).observe(
                time.perf_counter() - started
            )


class _HasStatus(Protocol):
    @property
    def status(self) -> Any: ...


P = ParamSpec("P")
R = TypeVar("R", bound=_HasStatus)


def _snake(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name.removesuffix("Error")).lower()


def counts_order_outcome(operation: str) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Count each call of an order operation as its resulting status (`accepted`,
    `payment_failed`, ...) or as the error it raised (`unavailable`, `price_changed`, ...).
    """

    def decorate(func: Callable[P, R]) -> Callable[P, R]:
        @wraps(func)
        def counted(*args: P.args, **kwargs: P.kwargs) -> R:
            try:
                result = func(*args, **kwargs)
            except Exception as exc:
                ORDER_OUTCOMES.labels(operation, _snake(type(exc).__name__)).inc()
                raise
            ORDER_OUTCOMES.labels(operation, str(result.status).lower()).inc()
            return result

        return counted

    return decorate


_LOCKING = re.compile(r"\bFOR (?:NO KEY )?UPDATE\b")
_LOCKED_TABLE = re.compile(r"\bFROM\s+(\w+)")
_STARTED = "caf_lock_started"


@event.listens_for(Engine, "before_cursor_execute")
def _lock_started(conn: Any, cursor: Any, statement: str, *args: Any) -> None:
    if _LOCKING.search(statement):
        conn.info[_STARTED] = time.perf_counter()


@event.listens_for(Engine, "after_cursor_execute")
def _lock_acquired(conn: Any, cursor: Any, statement: str, *args: Any) -> None:
    # A statement that failed never gets here; the next locking statement resets the start.
    started = conn.info.pop(_STARTED, None)
    if started is not None:
        found = _LOCKED_TABLE.search(statement)
        table = found.group(1) if found else "unknown"
        LOCK_WAIT.labels(table).observe(time.perf_counter() - started)


class _Fixed(Collector):
    def __init__(self, families: list[Metric]) -> None:
        self.families = families

    def collect(self) -> Iterable[Metric]:
        return self.families


def database_families(
    agent_runs: Iterable[tuple[str, str | None, int]] | None,
) -> list[Metric]:
    """`caf_database_up`, and the agent runs by status and source unless the database
    could not be read (`agent_runs` is None). A run whose source is HEURISTIC is a fallback.
    """
    up = GaugeMetricFamily("caf_database_up", "1 if /metrics could read the database.")
    up.add_metric([], 0 if agent_runs is None else 1)
    if agent_runs is None:
        return [up]
    runs = CounterMetricFamily(
        "caf_agent_runs",
        "Agent runs by status and source; source HEURISTIC is a fallback (FR-59).",
        labels=["status", "source"],
    )
    for status, source, count in agent_runs:
        runs.add_metric([status, source or "NONE"], count)
    return [up, runs]


def render(database: list[Metric]) -> bytes:
    if "PROMETHEUS_MULTIPROC_DIR" in os.environ:
        registry = CollectorRegistry()
        multiprocess.MultiProcessCollector(registry)  # type: ignore[no-untyped-call]
        body = generate_latest(registry)
    else:
        body = generate_latest(REGISTRY)
    extra = CollectorRegistry()
    extra.register(_Fixed(database))
    return body + generate_latest(extra)
