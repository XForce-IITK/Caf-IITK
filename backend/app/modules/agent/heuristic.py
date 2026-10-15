"""Heuristic planner: the deterministic fallback when the LLM cannot be used (FR-59).

It drafts the same proposal types from the same forecast the LLM sees, and
submits them as tool calls through the same registry, so heuristic proposals get
exactly the validation, payload shape and expiry of LLM ones.

Rules, for the run's service date:
- an item at HIGH risk whose shortfall P-REPL_MAX can cover: replenish the shortfall;
- an item at HIGH risk whose shortfall is larger than P-REPL_MAX: propose disabling it;
- the next slot with pending orders: prep priority by pending portions, most first.
The registry refuses disable and replenish once the service window has opened.
"""

import json
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from app.modules.agent.forecast import Risk, Snapshot
from app.modules.agent.llm import ToolCall
from app.modules.agent.tools import Outcome, StagedProposal, ToolRegistry


@dataclass(frozen=True)
class HeuristicPlan:
    narrative: str
    proposals: list[StagedProposal]


def _shortfall(row: dict[str, Any]) -> int:
    expected = max(0, int(row["forecast_demand"]) - int(row["allocated"]))
    return max(0, expected - int(row["available"]))


def _calls(snapshot: Snapshot, report: dict[str, Any], repl_max: int) -> list[ToolCall]:
    calls: list[ToolCall] = []
    replenish: list[dict[str, Any]] = []
    for row in report["forecast"]:
        if row["risk"] != Risk.HIGH.value:
            continue
        shortfall = _shortfall(row)
        if 0 < shortfall <= repl_max:
            replenish.append({"item_id": row["item_id"], "additional_portions": shortfall})
        elif shortfall > repl_max:
            args = {
                "item_id": row["item_id"],
                "reason": "forecast demand exceeds what can be prepared",
                "rationale": f"Short by {shortfall} portions, more than P-REPL_MAX ({repl_max}).",
            }
            calls.append(ToolCall(f"h{len(calls)}", "propose_item_disable", json.dumps(args)))
    if replenish:
        args = {
            "lines": replenish,
            "rationale": "Forecast demand (recent service dates) exceeds available portions.",
        }
        calls.append(ToolCall(f"h{len(calls)}", "propose_replenishment_plan", json.dumps(args)))

    pending: dict[str, dict[str, int]] = defaultdict(dict)
    starts: dict[str, str] = {}
    for row in snapshot.pending_orders:
        pending[row["slot_id"]][row["item_id"]] = row["portions"]
        starts[row["slot_id"]] = row["starts_at"]
    for slot_id in sorted(pending, key=lambda s: starts[s]):
        items = sorted(pending[slot_id], key=lambda i: (-pending[slot_id][i], i))
        args = {
            "slot_id": slot_id,
            "item_ids": items,
            "rationale": "Items with the most pending portions first.",
        }
        calls.append(ToolCall(f"h{len(calls)}", "propose_prep_priority", json.dumps(args)))
    return calls


def plan(
    snapshot: Snapshot, report: dict[str, Any], registry: ToolRegistry, repl_max: int
) -> HeuristicPlan:
    proposals: list[StagedProposal] = []
    prep_done = False
    for call in _calls(snapshot, report, repl_max):
        if call.name == "propose_prep_priority" and prep_done:
            continue
        result = registry.dispatch(call)
        if result.outcome is Outcome.OK and result.staged is not None:
            proposals.append(result.staged)
            # Only the next slot that can still be prioritised (its start not yet passed).
            prep_done = prep_done or call.name == "propose_prep_priority"
    high = [row["item_name"] for row in report["forecast"] if row["risk"] == Risk.HIGH.value]
    risk_text = f"High stock-out risk: {', '.join(high)}." if high else "No item is at high risk."
    narrative = (
        f"Heuristic briefing (the LLM was not used). {risk_text} "
        f"{len(proposals)} proposal(s) drafted for approval."
    )
    return HeuristicPlan(narrative, proposals)
