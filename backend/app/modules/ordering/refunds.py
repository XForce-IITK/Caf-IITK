"""Which authorisations a refund is taken from. Pure: no database, clock or I/O.

An order is paid by one authorisation at placement plus one for each modification
that raised its price (FR-36), and mockpay refuses a refund larger than what is
left of the authorisation it names. Each refund record (exactly one per cancel or
price-lowering modification, FR-39) is therefore sent as one or more parts.

The order's refunds, in the order they were recorded, are laid end to end over its
authorisations, oldest first. A new authorisation only ever extends the end, so
the parts of a refund recorded earlier never change, and a retry of any refund
sends exactly the parts it sent before.
"""

import uuid
from dataclasses import dataclass


class InsufficientChargesError(Exception):
    """The refunds add up to more than was charged; the order's accounting is wrong."""


@dataclass(frozen=True)
class RefundPart:
    reference: str
    auth_id: uuid.UUID
    amount_paise: int


def refund_parts(
    charges: list[tuple[uuid.UUID, int]],
    refunds: list[tuple[uuid.UUID, int]],
    refund_id: uuid.UUID,
) -> list[RefundPart]:
    """The parts of `refund_id`.

    `charges` are the approved authorisations as (payment id, amount), oldest first;
    `refunds` are the order's refund records as (payment id, amount) in the order
    they were recorded, `refund_id` among them. A refund sent as a single part
    keeps its record id as the reference; parts of a split one get `<id>:<n>`.
    """
    taken_before = 0
    for current_id, amount in refunds:
        if current_id == refund_id:
            break
        taken_before += amount
    else:
        raise ValueError(f"refund {refund_id} is not among the order's refunds")

    parts: list[tuple[uuid.UUID, int]] = []
    position = 0
    remaining = amount
    for auth_id, charged in charges:
        start, end = position, position + charged
        position = end
        # This charge's overlap with [taken_before, taken_before + amount).
        overlap_start = max(start, taken_before + (amount - remaining))
        overlap = min(end, taken_before + amount) - overlap_start
        if overlap > 0:
            parts.append((auth_id, overlap))
            remaining -= overlap
        if remaining == 0:
            break
    if remaining:
        raise InsufficientChargesError(f"refund {refund_id} exceeds what was charged")
    if len(parts) == 1:
        return [RefundPart(str(refund_id), parts[0][0], parts[0][1])]
    return [
        RefundPart(f"{refund_id}:{n}", auth_id, part)
        for n, (auth_id, part) in enumerate(parts, start=1)
    ]
