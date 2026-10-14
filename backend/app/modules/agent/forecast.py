"""The planning report's numbers (FR-52), computed from the tool data alone.

Pure functions, so the report is reproducible and testable without a database
or an LLM. The LLM adds judgement on top (which proposals to draft and why);
the heuristic planner (FR-59) reuses the same forecast.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any

# Forecast demand at or above this share of the available portions is MEDIUM risk.
MEDIUM_RISK_SHARE = 0.7


class Risk(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass(frozen=True)
class Snapshot:
    """What the five read tools return for one service date (rows as JSON-ready dicts)."""

    service_date: str
    pending_orders: list[dict[str, Any]]
    inventory_levels: list[dict[str, Any]]
    slot_utilisation: list[dict[str, Any]]
    historical_demand: list[dict[str, Any]]
    menu_config: list[dict[str, Any]]

    def as_tool_data(self) -> dict[str, Any]:
        return {
            "service_date": self.service_date,
            "get_pending_orders": self.pending_orders,
            "get_inventory_levels": self.inventory_levels,
            "get_slot_utilisation": self.slot_utilisation,
            "get_historical_demand": self.historical_demand,
            "get_menu_config": self.menu_config,
        }


def demand_summary(snapshot: Snapshot) -> list[dict[str, Any]]:
    """Pending portions per item per slot, in slot order."""
    names = {row["item_id"]: row["name"] for row in snapshot.menu_config}
    rows = sorted(
        snapshot.pending_orders, key=lambda r: (r["starts_at"], names.get(r["item_id"], ""))
    )
    return [
        {
            "item_id": row["item_id"],
            "item_name": names.get(row["item_id"]),
            "slot_id": row["slot_id"],
            "slot_start": row["starts_at"],
            "portions": row["portions"],
        }
        for row in rows
    ]


def _forecast_total(item_id: str, allocated: int, history: list[dict[str, Any]]) -> int:
    """Mean portions per past service date (a missing date counts as 0), else today's allocation."""
    dates = {row["service_date"] for row in history}
    if not dates:
        return allocated
    total: int = sum(int(row["portions"]) for row in history if row["item_id"] == item_id)
    return max(allocated, round(total / len(dates)))


def forecast(snapshot: Snapshot, now: datetime) -> list[dict[str, Any]]:
    """Per item: available portions, forecast demand, predicted stock-out slot and risk.

    Demand still to come (forecast minus already allocated) is spread evenly over
    the slots that have not started; the stock-out slot is the first in which the
    cumulative expected demand reaches the available portions.
    """
    names = {row["item_id"]: row["name"] for row in snapshot.menu_config}
    upcoming = sorted(
        (s for s in snapshot.slot_utilisation if datetime.fromisoformat(s["starts_at"]) > now),
        key=lambda s: s["starts_at"],
    )

    result = []
    for level in sorted(snapshot.inventory_levels, key=lambda r: names.get(r["item_id"], "")):
        item_id = level["item_id"]
        if item_id not in names:
            continue  # not ACTIVE any more
        available, allocated = level["available"], level["allocated"]
        forecast_demand = _forecast_total(item_id, allocated, snapshot.historical_demand)
        expected = max(0, forecast_demand - allocated)
        stockout = _stockout_slot(available, expected, upcoming)
        if available == 0 or (expected > 0 and expected >= available):
            risk = Risk.HIGH
        elif expected >= MEDIUM_RISK_SHARE * available:
            risk = Risk.MEDIUM
        else:
            risk = Risk.LOW
        result.append(
            {
                "item_id": item_id,
                "item_name": names[item_id],
                "available": available,
                "allocated": allocated,
                "forecast_demand": forecast_demand,
                "stockout_slot_id": stockout["slot_id"] if stockout else None,
                "stockout_slot_start": stockout["starts_at"] if stockout else None,
                "risk": risk.value,
            }
        )
    return result


def _stockout_slot(
    available: int, expected: int, upcoming: list[dict[str, Any]]
) -> dict[str, Any] | None:
    if not upcoming:
        return None
    if available == 0:
        return upcoming[0]
    per_slot = expected / len(upcoming)
    cumulative = 0.0
    for slot in upcoming:
        cumulative += per_slot
        if cumulative >= available:
            return slot
    return None


def build_report(snapshot: Snapshot, now: datetime) -> dict[str, Any]:
    return {
        "service_date": snapshot.service_date,
        "generated_at": now.isoformat(),
        "demand_summary": demand_summary(snapshot),
        "forecast": forecast(snapshot, now),
    }
