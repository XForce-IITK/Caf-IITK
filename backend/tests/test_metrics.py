"""NFR-31 tests TC-NFR31: readiness and the Prometheus metrics at GET /metrics.

Tests run caf-api in one process, so they read samples from the default registry.
The gunicorn test checks that the samples of several processes are added up.
"""

import os
import re
import signal
import subprocess
import sys
import threading
import time
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast

import httpx
import pytest
from conftest import BACKEND_DIR, _free_port
from fastapi import FastAPI
from fastapi.testclient import TestClient
from prometheus_client import REGISTRY
from prometheus_client.parser import text_string_to_metric_families
from sqlalchemy import Engine, create_engine, select
from sqlalchemy.orm import Session
from test_order_place import (  # noqa: F401  (api, gateway, menu, set_clock are fixtures)
    PAYABLE,
    _add,
    _cart,
    _headers,
    _user,
    api,
    gateway,
    menu,
    set_clock,
)

from app.db.session import get_session
from app.models.agent import AgentRun
from app.models.catalogue import MenuItem
from app.models.enums import AgentRunStatus, AgentSource, AgentTrigger, ItemCategory

# Nothing listens on port 1, so every connection is refused at once.
UNREACHABLE = "postgresql+psycopg://caf:caf@127.0.0.1:1/caf"
UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-")


def _sample(name: str, **labels: str) -> float:
    return REGISTRY.get_sample_value(name, labels) or 0.0


def _scrape(client: TestClient | httpx.Client) -> dict[tuple[str, frozenset[Any]], float]:
    response = client.get("/metrics")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    return {
        (sample.name, frozenset(sample.labels.items())): sample.value
        for family in text_string_to_metric_families(response.text)
        for sample in family.samples
    }


@pytest.fixture
def no_database(client: TestClient) -> Iterator[TestClient]:
    """caf-api with the database unreachable."""
    engine = create_engine(UNREACHABLE, connect_args={"connect_timeout": 1})

    def unreachable() -> Iterator[Session]:
        with Session(engine) as session:
            yield session

    cast(FastAPI, client.app).dependency_overrides[get_session] = unreachable
    yield client
    engine.dispose()


def test_tc_nfr31_ready_when_the_database_answers(db_client: TestClient) -> None:
    response = db_client.get("/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


def test_tc_nfr31_not_ready_without_the_database(no_database: TestClient) -> None:
    started = time.monotonic()
    response = no_database.get("/ready")
    assert response.status_code == 503
    assert response.headers["Retry-After"] == "5"
    assert response.json() == {"status": "unavailable"}
    # NFR-16: an answer within 5 s, not a hang.
    assert time.monotonic() - started < 5


def test_tc_nfr31_liveness_needs_no_database(no_database: TestClient) -> None:
    assert no_database.get("/health").status_code == 200


def test_tc_nfr31_requests_are_timed_per_route_template(client: TestClient) -> None:
    route = "/api/v1/orders/{order_id}"
    before = _sample(
        "caf_http_request_duration_seconds_count", method="GET", route=route, status="401"
    )
    unmatched_before = _sample(
        "caf_http_request_duration_seconds_count", method="GET", route="<unmatched>", status="404"
    )

    for _ in range(3):
        assert client.get(f"/api/v1/orders/{uuid.uuid4()}").status_code == 401
    assert client.get(f"/no-such-page/{uuid.uuid4()}").status_code == 404

    labels = frozenset({"method": "GET", "route": route, "status": "401"}.items())
    scraped = _scrape(client)
    assert scraped[("caf_http_request_duration_seconds_count", labels)] == before + 3
    assert scraped[("caf_http_request_duration_seconds_sum", labels)] > 0
    unmatched = frozenset({"method": "GET", "route": "<unmatched>", "status": "404"}.items())
    assert scraped[("caf_http_request_duration_seconds_count", unmatched)] == unmatched_before + 1
    # One series per route, never one per order id or probed path.
    routes = {dict(labels).get("route", "") for _, labels in scraped}
    assert not any(UUID.search(route) for route in routes)


def test_tc_nfr31_order_outcomes_and_lock_waits_are_counted(
    api: TestClient, engine: Engine, menu: dict[str, Any]
) -> None:
    student = _user(engine)
    accepted = _sample("caf_order_outcomes_total", operation="place", outcome="accepted")
    price_changed = _sample("caf_order_outcomes_total", operation="place", outcome="price_changed")
    inventory_locks = _sample("caf_db_lock_wait_seconds_count", table="daily_inventory")
    slot_locks = _sample("caf_db_lock_wait_seconds_count", table="slots")

    assert (
        api.post("/api/v1/orders", json=_cart(menu), headers=_headers(student)).status_code == 201
    )
    stale = _cart(menu, quoted=PAYABLE - 100)
    assert api.post("/api/v1/orders", json=stale, headers=_headers(student)).status_code == 409

    scraped = _scrape(api)
    place = {"operation": "place"}
    assert scraped[
        ("caf_order_outcomes_total", frozenset((place | {"outcome": "accepted"}).items()))
    ] == (accepted + 1)
    assert scraped[
        ("caf_order_outcomes_total", frozenset((place | {"outcome": "price_changed"}).items()))
    ] == (price_changed + 1)
    # Both placements lock the inventory rows; only the accepted one gets as far as the slot.
    assert _sample("caf_db_lock_wait_seconds_count", table="daily_inventory") >= inventory_locks + 2
    assert _sample("caf_db_lock_wait_seconds_count", table="slots") >= slot_locks + 1


def test_tc_nfr31_lock_wait_time_includes_waiting_for_another_transaction(engine: Engine) -> None:
    item = MenuItem(id=uuid.uuid4(), name="Samosa", category=ItemCategory.SNACK, price_paise=1500)
    _add(engine, item)
    waited_before = _sample("caf_db_lock_wait_seconds_sum", table="menu_items")
    locked = threading.Event()

    def hold_lock() -> None:
        with Session(engine) as session, session.begin():
            session.scalars(select(MenuItem).where(MenuItem.id == item.id).with_for_update()).one()
            locked.set()
            time.sleep(0.5)

    holder = threading.Thread(target=hold_lock)
    holder.start()
    try:
        assert locked.wait(10)
        with Session(engine) as session, session.begin():
            session.scalars(select(MenuItem).where(MenuItem.id == item.id).with_for_update()).one()
    finally:
        holder.join()
        with Session(engine) as session, session.begin():
            session.delete(session.get(MenuItem, item.id))

    # The second lock waited for most of the 0.5 s the first was held.
    assert _sample("caf_db_lock_wait_seconds_sum", table="menu_items") - waited_before >= 0.3


def test_tc_nfr31_agent_runs_and_fallbacks_are_counted(
    db_client: TestClient, engine: Engine
) -> None:
    def runs(scraped: dict[tuple[str, frozenset[Any]], float], source: str) -> float:
        labels = frozenset({"status": "SUCCEEDED", "source": source}.items())
        return scraped.get(("caf_agent_runs_total", labels), 0.0)

    before = _scrape(db_client)
    # Agent runs execute in caf-worker, so /metrics counts them from the table.
    _add(
        engine,
        *(
            AgentRun(trigger=AgentTrigger.SCHEDULED, status=AgentRunStatus.SUCCEEDED, source=source)
            for source in (AgentSource.LLM, AgentSource.HEURISTIC, AgentSource.HEURISTIC)
        ),
    )

    after = _scrape(db_client)
    assert after[("caf_database_up", frozenset())] == 1
    assert runs(after, "LLM") == runs(before, "LLM") + 1
    assert runs(after, "HEURISTIC") == runs(before, "HEURISTIC") + 2


def test_tc_nfr31_metrics_are_served_while_the_database_is_down(no_database: TestClient) -> None:
    scraped = _scrape(no_database)
    assert scraped[("caf_database_up", frozenset())] == 0
    assert not any(name == "caf_agent_runs_total" for name, _ in scraped)
    assert any(name == "caf_http_request_duration_seconds_count" for name, _ in scraped)


@pytest.mark.skipif(sys.platform == "win32", reason="gunicorn does not run on Windows")
def test_tc_nfr31_metrics_add_up_across_gunicorn_workers(tmp_path: Path) -> None:
    """The production command (Dockerfile CMD): two workers, one total."""
    url = f"http://127.0.0.1:{_free_port()}"
    env = os.environ | {"PROMETHEUS_MULTIPROC_DIR": str(tmp_path / "metrics")}
    command = [sys.executable, "-m", "gunicorn", "app.main:app", "-c", "gunicorn.conf.py"]
    command += ["-b", url.removeprefix("http://")]
    server = subprocess.Popen(command, cwd=BACKEND_DIR, env=env, start_new_session=True)
    try:
        with httpx.Client(base_url=url, timeout=5) as http:
            # Every answered request is counted, including the polls until start-up.
            answered = 0
            deadline = time.monotonic() + 60
            while answered == 0:
                try:
                    answered += http.get("/health").status_code == 200
                except httpx.HTTPError:
                    assert time.monotonic() < deadline, "gunicorn did not start"
                    time.sleep(0.2)
            # A fresh connection per request, so both workers get some.
            for _ in range(20):
                assert httpx.get(f"{url}/health", timeout=5).status_code == 200

            health = frozenset({"method": "GET", "route": "/health", "status": "200"}.items())
            # Whichever worker answers the scrape reports the total of both.
            counts = [_scrape(http)[("caf_http_request_duration_seconds_count", health)]]
            counts += [
                _scrape(httpx.Client(base_url=url))[
                    ("caf_http_request_duration_seconds_count", health)
                ]
                for _ in range(5)
            ]
            assert counts == [answered + 20] * 6
    finally:
        os.killpg(server.pid, signal.SIGTERM)
        server.wait(timeout=20)
