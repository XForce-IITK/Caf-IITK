"""The monthly LLM spend report (NFR-42, CAFIITK-191).

LLM usage shall stay within P-AGENT_DAILY_CAP requests a day and USD 5 a month.
The cap is enforced before every request (llm.consume_daily_budget); this report
shows what was actually used, from `agent_llm_calls`.

Run on the deployed stack, in the repository root on the instance:

    docker compose -f docker-compose.prod.yml exec api \
        python -m app.modules.agent.spend [--month 2026-11]

Only OK rows were billed by the provider: a CACHED answer made no provider call, and
an ERROR row carries no token counts. The exit status is 1 when the month is over
budget, a day is over the cap, or a model has no price below.
"""

import argparse
import sys
from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal

from app.core import clock
from app.core.config import get_settings
from app.db.session import get_sessionmaker
from app.modules.agent.repository import RunRepository

MONTHLY_BUDGET_USD = Decimal("5")
# USD per million input and output tokens, OpenAI list prices (checked Nov 2026).
# Matched by prefix, since the provider reports dated names such as gpt-4o-mini-2024-07-18.
PRICES_PER_MTOK: dict[str, tuple[Decimal, Decimal]] = {
    "gpt-4o-mini": (Decimal("0.15"), Decimal("0.60")),
}
MILLION = Decimal(1_000_000)


@dataclass(frozen=True)
class Usage:
    """One IST day's LLM calls for one model and outcome."""

    day: date
    model: str
    outcome: str
    requests: int
    prompt_tokens: int
    completion_tokens: int


@dataclass(frozen=True)
class DayLine:
    day: date
    billed: int
    cached: int
    errors: int
    prompt_tokens: int
    completion_tokens: int
    cost_usd: Decimal


@dataclass(frozen=True)
class MonthReport:
    month: date
    daily_cap: int
    days: tuple[DayLine, ...]
    cost_usd: Decimal
    unpriced_models: tuple[str, ...]

    @property
    def days_over_cap(self) -> tuple[date, ...]:
        return tuple(d.day for d in self.days if d.billed > self.daily_cap)

    @property
    def within_limits(self) -> bool:
        return (
            self.cost_usd <= MONTHLY_BUDGET_USD
            and not self.days_over_cap
            and not self.unpriced_models
        )


def price_of(model: str) -> tuple[Decimal, Decimal] | None:
    matches = [name for name in PRICES_PER_MTOK if model.startswith(name)]
    return PRICES_PER_MTOK[max(matches, key=len)] if matches else None


def cost_usd(model: str, prompt_tokens: int, completion_tokens: int) -> Decimal | None:
    price = price_of(model)
    if price is None:
        return None
    return (prompt_tokens * price[0] + completion_tokens * price[1]) / MILLION


def month_bounds(month: date) -> tuple[datetime, datetime]:
    """The IST month containing `month`, as [start, end)."""
    start = month.replace(day=1)
    end = date(start.year + start.month // 12, start.month % 12 + 1, 1)
    return (
        datetime.combine(start, time.min, tzinfo=clock.IST),
        datetime.combine(end, time.min, tzinfo=clock.IST),
    )


def build_report(month: date, usage: list[Usage], daily_cap: int) -> MonthReport:
    days: dict[date, list[Usage]] = {}
    for row in usage:
        days.setdefault(row.day, []).append(row)
    unpriced: set[str] = set()
    lines = []
    for day, rows in sorted(days.items()):
        billed = [r for r in rows if r.outcome == "OK"]
        cost = Decimal(0)
        for r in billed:
            row_cost = cost_usd(r.model, r.prompt_tokens, r.completion_tokens)
            if row_cost is None:
                unpriced.add(r.model)
            else:
                cost += row_cost
        lines.append(
            DayLine(
                day=day,
                billed=sum(r.requests for r in billed),
                cached=sum(r.requests for r in rows if r.outcome == "CACHED"),
                errors=sum(r.requests for r in rows if r.outcome == "ERROR"),
                prompt_tokens=sum(r.prompt_tokens for r in billed),
                completion_tokens=sum(r.completion_tokens for r in billed),
                cost_usd=cost,
            )
        )
    return MonthReport(
        month=month.replace(day=1),
        daily_cap=daily_cap,
        days=tuple(lines),
        cost_usd=sum((d.cost_usd for d in lines), Decimal(0)),
        unpriced_models=tuple(sorted(unpriced)),
    )


def render(report: MonthReport) -> str:
    out = [
        f"LLM spend for {report.month:%B %Y} (IST days)",
        "",
        f"{'Day':<12}{'Billed':>8}{'Cached':>8}{'Errors':>8}{'In tokens':>12}{'Out tokens':>12}"
        f"{'USD':>10}",
    ]
    for d in report.days:
        out.append(
            f"{d.day.isoformat():<12}{d.billed:>8}{d.cached:>8}{d.errors:>8}"
            f"{d.prompt_tokens:>12}{d.completion_tokens:>12}{d.cost_usd:>10.4f}"
        )
    if not report.days:
        out.append("(no LLM requests)")
    busiest = max((d.billed for d in report.days), default=0)
    out += [
        "",
        f"Busiest day: {busiest} billed requests (P-AGENT_DAILY_CAP {report.daily_cap})",
        f"Month total: USD {report.cost_usd:.4f} of USD {MONTHLY_BUDGET_USD}",
    ]
    if report.days_over_cap:
        out.append("Over the daily cap on: " + ", ".join(map(str, report.days_over_cap)))
    if report.unpriced_models:
        out.append("No price for: " + ", ".join(report.unpriced_models))
    out.append("Within NFR-42" if report.within_limits else "NOT within NFR-42")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--month",
        type=lambda s: datetime.strptime(s, "%Y-%m").date(),
        default=clock.now().date(),
        help="YYYY-MM, default the current IST month",
    )
    month = parser.parse_args(argv).month
    start, end = month_bounds(month)
    with get_sessionmaker()() as session:
        rows = RunRepository(session).llm_usage_by_day(start, end)
    report = build_report(month, [Usage(*row) for row in rows], get_settings().agent_daily_cap)
    print(render(report))
    return 0 if report.within_limits else 1


if __name__ == "__main__":
    sys.exit(main())
