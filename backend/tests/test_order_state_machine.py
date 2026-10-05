"""FR-29 / FR-16: Table 4.6-A as a pure function."""

import itertools

import pytest

from app.models.enums import OrderStatus as S
from app.modules.ordering.state_machine import Effects, IllegalTransitionError, transition

KEEP = Effects()
RELEASE_BOTH = Effects(releases_portions=True, releases_seat=True)
RELEASE_SEAT = Effects(releases_seat=True)

LEGAL = {
    (None, S.PENDING_PAYMENT): KEEP,
    (S.PENDING_PAYMENT, S.ACCEPTED): KEEP,
    (S.PENDING_PAYMENT, S.PAYMENT_FAILED): RELEASE_BOTH,
    (S.ACCEPTED, S.PREPARING): KEEP,
    (S.ACCEPTED, S.CANCELLED): RELEASE_BOTH,
    (S.PREPARING, S.CANCELLED): RELEASE_SEAT,
    (S.PREPARING, S.READY): KEEP,
    (S.READY, S.CANCELLED): RELEASE_SEAT,
    (S.READY, S.PICKED_UP): KEEP,
    (S.READY, S.NO_SHOW): KEEP,
}


@pytest.mark.parametrize(("pair", "effects"), LEGAL.items())
def test_legal_transition_has_the_effects_of_table_4_6_a(
    pair: tuple[S | None, S], effects: Effects
) -> None:
    assert transition(*pair) == effects


@pytest.mark.parametrize("pair", [p for p in itertools.product([None, *S], S) if p not in LEGAL])
def test_every_other_transition_is_illegal(pair: tuple[S | None, S]) -> None:
    with pytest.raises(IllegalTransitionError) as raised:
        transition(*pair)
    assert (raised.value.from_status, raised.value.to_status) == pair
