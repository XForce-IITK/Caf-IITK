"""The permission matrix matches SRS Table 4.1-A exactly (FR-6)."""

import pytest

from app.models.enums import Role
from app.modules.identity.permissions import ROLE_PERMISSIONS, Permission, is_permitted

P = Permission
S, K, A = Role.STUDENT, Role.KITCHEN, Role.ADMIN

# Table 4.1-A, row by row: the roles allowed to perform each action.
TABLE_4_1_A: dict[Permission, set[Role]] = {
    P.BROWSE_MENU: {S, K, A},
    P.MANAGE_OWN_ORDERS: {S},
    P.VIEW_OWN_ORDERS: {S},
    P.OPERATE_KITCHEN: {K, A},
    P.FLAG_ITEM: {K, A},
    P.MANAGE_MENU: {A},
    P.MANAGE_CAPACITY: {A},
    P.MANAGE_PRICING: {A},
    P.CANCEL_ANY_ORDER: {A},
    P.VIEW_ALL: {A},
    P.MANAGE_STAFF: {A},
    P.MANAGE_AGENT: {A},
}


def test_table_covers_every_permission_and_role() -> None:
    assert set(TABLE_4_1_A) == set(Permission)
    assert set(ROLE_PERMISSIONS) == set(Role)


@pytest.mark.parametrize("permission", list(Permission))
@pytest.mark.parametrize("role", list(Role))
def test_matrix_matches_table_4_1_a(role: Role, permission: Permission) -> None:
    assert is_permitted(role, permission) == (role in TABLE_4_1_A[permission])


@pytest.mark.parametrize(
    "permission", [P.MANAGE_MENU, P.MANAGE_PRICING, P.MANAGE_CAPACITY, P.CANCEL_ANY_ORDER]
)
def test_kitchen_denied_price_discount_inventory_and_cancellation(permission: Permission) -> None:
    # FR-6: "Kitchen Staff shall be denied every price, discount, inventory and
    # order-cancellation operation."
    assert not is_permitted(K, permission)
