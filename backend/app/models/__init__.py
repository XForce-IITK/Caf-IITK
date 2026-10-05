"""All ORM models, imported here so Alembic sees the full metadata.

Core data model: SADD Figure 2.5; audit_log from Figure 2.6. Agent tables
(agent_runs, proposals, ...) arrive with the Agent epic.
"""

from app.models.capacity import DailyInventory, ServiceDay, Slot
from app.models.catalogue import DiscountRule, DiscountRuleItem, MenuItem
from app.models.identity import RefreshToken, User
from app.models.ordering import (
    IdempotencyKey,
    Order,
    OrderLine,
    OrderModification,
    OrderTransition,
    Payment,
    PriceSnapshot,
)
from app.models.platform import AuditLog, RateLimit, Setting

__all__ = [
    "AuditLog",
    "DailyInventory",
    "DiscountRule",
    "DiscountRuleItem",
    "IdempotencyKey",
    "MenuItem",
    "Order",
    "OrderLine",
    "OrderModification",
    "OrderTransition",
    "Payment",
    "PriceSnapshot",
    "RateLimit",
    "RefreshToken",
    "ServiceDay",
    "Setting",
    "Slot",
    "User",
]
