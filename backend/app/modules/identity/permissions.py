"""The permission matrix, SRS Table 4.1-A (FR-6).

Anything not listed for a role is denied. Endpoints declare the permission they
need with `require_permission(...)` (dependencies.py) instead of checking roles.
"""

from enum import StrEnum

from app.models.enums import Role


class Permission(StrEnum):
    BROWSE_MENU = "browse_menu"  # browse menu and slots
    MANAGE_OWN_ORDERS = "manage_own_orders"  # quote, place, modify, cancel own order
    VIEW_OWN_ORDERS = "view_own_orders"  # own orders and history
    OPERATE_KITCHEN = "operate_kitchen"  # view kitchen queue; advance order state
    FLAG_ITEM = "flag_item"  # set/clear temporary-unavailable flag
    MANAGE_MENU = "manage_menu"  # onboard, edit, remove menu items; set prices
    MANAGE_CAPACITY = "manage_capacity"  # inventory, service window and slots
    MANAGE_PRICING = "manage_pricing"  # discount rules, subsidy, eligibility
    CANCEL_ANY_ORDER = "cancel_any_order"  # with reason
    VIEW_ALL = "view_all"  # all orders, utilisation, audit log
    MANAGE_STAFF = "manage_staff"  # create/deactivate staff accounts
    MANAGE_AGENT = "manage_agent"  # trigger agent run; approve/reject proposals


ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.STUDENT: frozenset(
        {Permission.BROWSE_MENU, Permission.MANAGE_OWN_ORDERS, Permission.VIEW_OWN_ORDERS}
    ),
    Role.KITCHEN: frozenset(
        {Permission.BROWSE_MENU, Permission.OPERATE_KITCHEN, Permission.FLAG_ITEM}
    ),
    Role.ADMIN: frozenset(
        {
            Permission.BROWSE_MENU,
            Permission.OPERATE_KITCHEN,
            Permission.FLAG_ITEM,
            Permission.MANAGE_MENU,
            Permission.MANAGE_CAPACITY,
            Permission.MANAGE_PRICING,
            Permission.CANCEL_ANY_ORDER,
            Permission.VIEW_ALL,
            Permission.MANAGE_STAFF,
            Permission.MANAGE_AGENT,
        }
    ),
}


def is_permitted(role: Role, permission: Permission) -> bool:
    return permission in ROLE_PERMISSIONS[role]
