"""The order of a slot's aggregated item totals in the kitchen queue (FR-42, FR-54)."""

import uuid
from collections.abc import Mapping, Sequence


def order_item_totals(
    counts: Mapping[uuid.UUID, int],
    names: Mapping[uuid.UUID, str],
    priority: Sequence[uuid.UUID] | None,
) -> list[uuid.UUID]:
    """The items with a count, in the order the kitchen should prepare them.

    Without an approved prep-priority list: descending count. With one: its items
    first, in its order, then any item it does not name (demand that arrived after
    it was drafted) by descending count. Listed items with nothing left to prepare
    are left out. Ties fall back to name, then ID, so the order is stable.
    """

    def by_count(item_id: uuid.UUID) -> tuple[int, str, str]:
        return (-counts[item_id], names[item_id].lower(), str(item_id))

    if not priority:
        return sorted(counts, key=by_count)
    listed = [item_id for item_id in dict.fromkeys(priority) if item_id in counts]
    rest = sorted(counts.keys() - set(listed), key=by_count)
    return listed + rest
