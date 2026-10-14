"""All ORM models, imported here so Alembic sees the full metadata.

Core data model: SADD Figure 2.5. Audit, agent and proposal data: Figure 2.6.
"""

from app.models.agent import AgentLlmCall, AgentRun, AgentToolCall, Proposal
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
    "AgentLlmCall",
    "AgentRun",
    "AgentToolCall",
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
    "Proposal",
    "RateLimit",
    "RefreshToken",
    "ServiceDay",
    "Setting",
    "Slot",
    "User",
]
