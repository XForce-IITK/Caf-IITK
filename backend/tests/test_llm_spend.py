"""The monthly LLM spend report (NFR-42, CAFIITK-191)."""

import uuid
from collections.abc import Iterator
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.models.agent import AgentLlmCall, AgentRun
from app.models.enums import AgentRunStatus, AgentSource, AgentTrigger
from app.modules.agent.repository import RunRepository
from app.modules.agent.spend import (
    Usage,
    build_report,
    cost_usd,
    main,
    month_bounds,
    render,
)

NOV = date(2026, 11, 1)


def _usage(day: int, requests: int, outcome: str = "OK", model: str = "gpt-4o-mini") -> Usage:
    return Usage(date(2026, 11, day), model, outcome, requests, 1000 * requests, 200 * requests)


def test_a_million_tokens_each_way_costs_the_list_price() -> None:
    assert cost_usd("gpt-4o-mini", 1_000_000, 1_000_000) == Decimal("0.75")


def test_dated_model_names_are_priced_by_prefix() -> None:
    assert cost_usd("gpt-4o-mini-2024-07-18", 2_000_000, 0) == Decimal("0.30")


def test_an_unknown_model_has_no_price() -> None:
    assert cost_usd("some-other-model", 10, 10) is None


def test_only_billed_requests_cost_money() -> None:
    report = build_report(NOV, [_usage(5, 2), _usage(5, 3, "CACHED"), _usage(5, 1, "ERROR")], 50)

    [day] = report.days
    assert (day.billed, day.cached, day.errors) == (2, 3, 1)
    # 2000 input and 400 output tokens.
    assert report.cost_usd == Decimal("0.00054")
    assert report.within_limits


def test_tc_nfr42_a_day_over_the_cap_is_reported() -> None:
    report = build_report(NOV, [_usage(5, 50), _usage(6, 51)], 50)

    assert report.days_over_cap == (date(2026, 11, 6),)
    assert not report.within_limits
    assert "Over the daily cap on: 2026-11-06" in render(report)


def test_tc_nfr42_a_month_over_usd_5_is_reported() -> None:
    # 10 million output tokens at USD 0.60 per million.
    over = Usage(date(2026, 11, 5), "gpt-4o-mini", "OK", 40, 0, 10_000_000)
    report = build_report(NOV, [over], 50)

    assert report.cost_usd == Decimal("6")
    assert not report.within_limits
    assert "NOT within NFR-42" in render(report)


def test_an_unpriced_model_fails_the_report_rather_than_counting_as_free() -> None:
    report = build_report(NOV, [_usage(5, 1, model="some-other-model")], 50)

    assert report.unpriced_models == ("some-other-model",)
    assert not report.within_limits


def test_month_bounds_wrap_the_year() -> None:
    start, end = month_bounds(date(2026, 12, 17))

    assert (start.date(), end.date()) == (date(2026, 12, 1), date(2027, 1, 1))


@pytest.fixture
def session(engine: Engine) -> Iterator[Session]:
    with Session(engine) as session:
        yield session
        session.rollback()


def _run_with_calls(session: Session, started_at: datetime, *calls: tuple[str, int, int]) -> None:
    run = AgentRun(
        id=uuid.uuid4(),
        trigger=AgentTrigger.ON_DEMAND,
        status=AgentRunStatus.SUCCEEDED,
        source=AgentSource.LLM,
        started_at=started_at,
    )
    session.add(run)
    session.flush()
    for outcome, prompt, completion in calls:
        session.add(
            AgentLlmCall(
                run_id=run.id,
                model="gpt-4o-mini-2024-07-18",
                prompt_tokens=prompt,
                completion_tokens=completion,
                latency_ms=900,
                outcome=outcome,
            )
        )
    session.flush()


def test_usage_is_grouped_by_ist_day_and_outcome(session: Session) -> None:
    # 18:45 UTC on 4 Nov is 00:15 IST on 5 Nov.
    _run_with_calls(session, datetime(2026, 11, 4, 18, 45, tzinfo=UTC), ("OK", 100, 10))
    _run_with_calls(
        session,
        datetime(2026, 11, 5, 6, 0, tzinfo=UTC),
        ("OK", 300, 30),
        ("CACHED", 300, 30),
    )
    # 31 Oct IST: outside November.
    _run_with_calls(session, datetime(2026, 10, 31, 12, 0, tzinfo=UTC), ("OK", 999, 99))

    rows = RunRepository(session).llm_usage_by_day(*month_bounds(NOV))

    assert rows == [
        (date(2026, 11, 5), "gpt-4o-mini-2024-07-18", "CACHED", 1, 300, 30),
        (date(2026, 11, 5), "gpt-4o-mini-2024-07-18", "OK", 2, 400, 40),
    ]


def test_the_command_prints_the_month_and_passes_within_limits(
    configured_database: None, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["--month", "2026-01"]) == 0

    out = capsys.readouterr().out
    assert "LLM spend for January 2026" in out
    assert "Within NFR-42" in out
