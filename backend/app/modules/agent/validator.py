"""Output Validator (FR-58, SADD 2.3 and 6.6 layer 4): referential and bounds checks.

The tool registry checks a proposal's shape; this checks it against the run's
data before it can be staged:

- referential: every item is an ACTIVE menu item (AF-1, hallucinated entities);
  a replenished item has inventory for the date; a prep-priority item has
  pending demand in that slot (FR-54);
- bounds: each replenishment adds at most P-REPL_MAX portions, and the new total
  stays within the 0-500 portions an item can have (FR-14, FR-55; AF-3).

The same checks run again at approval (FR-57, CAFIITK-165), against the state at
that moment.
"""

from collections import defaultdict

from app.models.enums import ProposalType
from app.modules.agent.forecast import Snapshot

# FR-14: an item has 0-500 portions per service date (daily_inventory CHECK).
MAX_TOTAL_PORTIONS = 500


class ProposalRejectedError(ValueError):
    """The proposal fails a referential or bounds check; the message says why."""


class OutputValidator:
    def __init__(self, snapshot: Snapshot, repl_max: int) -> None:
        self._repl_max = repl_max
        self._active = {row["item_id"] for row in snapshot.menu_config}
        self._totals = {row["item_id"]: int(row["total"]) for row in snapshot.inventory_levels}
        self._pending: dict[str, set[str]] = defaultdict(set)
        for row in snapshot.pending_orders:
            self._pending[row["slot_id"]].add(row["item_id"])

    def _require_active(self, item_id: str) -> None:
        if item_id not in self._active:
            raise ProposalRejectedError(f"item {item_id} does not exist or is not ACTIVE")

    def check(
        self, proposal_type: ProposalType, payload: dict[str, object], slot_id: str | None
    ) -> None:
        if proposal_type is ProposalType.DISABLE:
            self._require_active(str(payload["item_id"]))
        elif proposal_type is ProposalType.PREP_PRIORITY:
            item_ids = payload["item_ids"]
            assert isinstance(item_ids, list) and slot_id is not None
            for item_id in map(str, item_ids):
                self._require_active(item_id)
                if item_id not in self._pending[slot_id]:
                    raise ProposalRejectedError(f"item {item_id} has no pending orders in the slot")
        else:
            lines = payload["lines"]
            assert isinstance(lines, list)
            for line in lines:
                item_id, extra = str(line["item_id"]), int(line["additional_portions"])
                self._require_active(item_id)
                if item_id not in self._totals:
                    raise ProposalRejectedError(f"item {item_id} has no inventory for the date")
                if extra > self._repl_max:
                    raise ProposalRejectedError(
                        f"{extra} additional portions exceed P-REPL_MAX ({self._repl_max})"
                    )
                if self._totals[item_id] + extra > MAX_TOTAL_PORTIONS:
                    raise ProposalRejectedError(
                        f"item {item_id} would exceed {MAX_TOTAL_PORTIONS} portions"
                    )
