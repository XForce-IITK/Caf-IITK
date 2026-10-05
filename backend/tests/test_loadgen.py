"""The concurrency harness itself: the live two-worker stack and the rush load generator.

The NFR-1 acceptance run (200 requests, 50 portions, 30 seats, 10 runs) is US-30;
these tests prove the harness measures correctly at a small scale.
"""

import asyncio
from collections.abc import Iterator

import httpx
import loadgen
import pytest
from conftest import LiveStack
from sqlalchemy import Engine, select, text, update
from sqlalchemy.orm import Session

from app.models.capacity import DailyInventory, Slot
from app.models.platform import Setting


@pytest.fixture
def rush_db(engine: Engine) -> Iterator[Engine]:
    yield engine
    with engine.begin() as connection:
        connection.execute(text("TRUNCATE users, menu_items, service_days, discount_rules CASCADE"))


def _menu_open(engine: Engine) -> str:
    with Session(engine) as session:
        value: str = session.scalars(
            select(Setting.value).where(Setting.key == loadgen.MENU_OPEN)
        ).one()
        return value


def test_live_stack_serves_the_api_and_mockpay(live_stack: LiveStack) -> None:
    assert len(set(live_stack.api_urls)) == 2
    for api_url in live_stack.api_urls:
        assert httpx.get(f"{api_url}/health").json() == {"status": "ok"}
    assert httpx.get(f"{live_stack.mockpay_url}/_control/outcome").json()["mode"] == "approve"


@pytest.mark.parametrize(
    ("portions", "seats", "accepted"),
    [(5, 3, 3), (2, 5, 2)],
    ids=["seats run out first", "portions run out first"],
)
def test_small_rush_across_two_processes_sells_exactly_what_exists(
    live_stack: LiveStack, rush_db: Engine, portions: int, seats: int, accepted: int
) -> None:
    (report,) = loadgen.run_rush(
        live_stack.api_urls, rush_db, requests=20, portions=portions, seats=seats, runs=1
    )

    assert report.ok, report.summary()
    assert (report.accepted, report.rejected) == (accepted, 20 - accepted)
    assert report.statuses == {201: accepted, 409: 20 - accepted}
    assert report.available_portions == portions - accepted
    assert report.remaining_seats == seats - accepted


def _rush(live_stack: LiveStack, engine: Engine) -> tuple[loadgen.Scenario, list[httpx.Response]]:
    with loadgen.menu_open_all_day(engine):
        scenario = loadgen.seed(engine, requests=6, portions=4, seats=2)
        return scenario, asyncio.run(loadgen.fire(live_stack.api_urls, scenario))


def test_requests_alternate_between_the_api_processes(
    live_stack: LiveStack, rush_db: Engine
) -> None:
    _, responses = _rush(live_stack, rush_db)
    hosts = [f"http://{r.request.url.host}:{r.request.url.port}" for r in responses]
    assert hosts == list(live_stack.api_urls) * 3


def test_verify_reports_an_oversold_counter(live_stack: LiveStack, rush_db: Engine) -> None:
    scenario, responses = _rush(live_stack, rush_db)
    assert loadgen.verify(rush_db, scenario, responses).ok
    # What a lost update would leave behind: one more portion and seat gone than orders made.
    with Session(rush_db) as session, session.begin():
        session.execute(
            update(DailyInventory)
            .where(DailyInventory.item_id == scenario.item_id)
            .values(allocated=DailyInventory.allocated + 1)
        )
        session.execute(
            update(Slot).where(Slot.id == scenario.slot_id).values(capacity=3, booked=3)
        )

    report = loadgen.verify(rush_db, scenario, responses)

    assert report.violations == ["portions allocated: 3, expected 2", "seats booked: 3, expected 2"]
    assert "FAILED" in report.summary()


def test_verify_reports_unexpected_responses(live_stack: LiveStack, rush_db: Engine) -> None:
    scenario, responses = _rush(live_stack, rush_db)
    conflict = next(r for r in responses if r.status_code == 409)
    responses[responses.index(conflict)] = httpx.Response(503, text="Busy, try again")

    report = loadgen.verify(rush_db, scenario, responses)

    assert report.violations == [
        "unexpected response 503: Busy, try again",
        "409 responses: 3, expected 4",
    ]


def test_script_prints_each_run_and_exits_zero(
    live_stack: LiveStack,
    rush_db: Engine,
    database_url: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    arguments = ["--database-url", database_url]
    for api_url in live_stack.api_urls:
        arguments += ["--base-url", api_url]
    arguments += ["--requests", "8", "--portions", "3", "--seats", "2", "--runs", "2"]

    assert loadgen.main(arguments) == 0

    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 2
    assert lines[0].startswith("run 1: accepted=2 rejected=6 portions_left=1 seats_left=0")
    assert lines[1].endswith("OK")


def test_script_exits_non_zero_when_a_run_fails(
    rush_db: Engine, database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    failed = loadgen.RunReport(violations=["seats booked: 31, expected 30"])
    monkeypatch.setattr(loadgen, "run_rush", lambda *args, **kwargs: [failed])

    assert loadgen.main(["--database-url", database_url]) == 1


def test_menu_open_is_restored_even_if_the_run_fails(rush_db: Engine) -> None:
    before = _menu_open(rush_db)

    with pytest.raises(RuntimeError), loadgen.menu_open_all_day(rush_db):
        assert _menu_open(rush_db) == "00:00"
        raise RuntimeError("boom")

    assert _menu_open(rush_db) == before
