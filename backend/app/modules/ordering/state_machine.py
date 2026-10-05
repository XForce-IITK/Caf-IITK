"""Order state machine, SRS Table 4.6-A (FR-29). Pure: no database, clock or I/O.

Each legal transition carries what happens to the order's portions and seat, so
FR-16 (when portions are returned) is decided here and nowhere else.
"""

from dataclasses import dataclass

from app.models.enums import OrderStatus


class IllegalTransitionError(Exception):
    """Not a row of Table 4.6-A: rejected with 409, nothing changes (FR-29)."""

    def __init__(self, from_status: OrderStatus | None, to_status: OrderStatus) -> None:
        super().__init__(f"illegal transition {from_status} -> {to_status}")
        self.from_status = from_status
        self.to_status = to_status


@dataclass(frozen=True)
class Effects:
    releases_portions: bool = False
    releases_seat: bool = False


_KEEP = Effects()
_RELEASE_BOTH = Effects(releases_portions=True, releases_seat=True)
# The food is already being made, so only the seat comes back (FR-16).
_RELEASE_SEAT = Effects(releases_seat=True)

_S = OrderStatus
_TRANSITIONS: dict[tuple[OrderStatus | None, OrderStatus], Effects] = {
    (None, _S.PENDING_PAYMENT): _KEEP,  # T1: placement allocates the holds itself
    (_S.PENDING_PAYMENT, _S.ACCEPTED): _KEEP,  # T2
    (_S.PENDING_PAYMENT, _S.PAYMENT_FAILED): _RELEASE_BOTH,  # T3
    (_S.ACCEPTED, _S.PREPARING): _KEEP,  # T5
    (_S.ACCEPTED, _S.CANCELLED): _RELEASE_BOTH,  # T6
    (_S.PREPARING, _S.CANCELLED): _RELEASE_SEAT,  # T7
    (_S.PREPARING, _S.READY): _KEEP,  # T8
    (_S.READY, _S.CANCELLED): _RELEASE_SEAT,  # T9
    (_S.READY, _S.PICKED_UP): _KEEP,  # T10: consumed
    (_S.READY, _S.NO_SHOW): _KEEP,  # T11
}
# T4 (modify) keeps the order ACCEPTED and swaps its holds; it is not a state change.


def transition(from_status: OrderStatus | None, to_status: OrderStatus) -> Effects:
    """The effects of a legal transition; IllegalTransitionError for any other."""
    try:
        return _TRANSITIONS[from_status, to_status]
    except KeyError:
        raise IllegalTransitionError(from_status, to_status) from None
