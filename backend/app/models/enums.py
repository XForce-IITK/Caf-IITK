from enum import StrEnum


class Role(StrEnum):
    STUDENT = "STUDENT"
    KITCHEN = "KITCHEN"
    ADMIN = "ADMIN"


class ItemCategory(StrEnum):
    MEAL = "MEAL"
    SNACK = "SNACK"
    BEVERAGE = "BEVERAGE"
    DESSERT = "DESSERT"


class ItemStatus(StrEnum):
    ACTIVE = "ACTIVE"
    REMOVED = "REMOVED"


class DiscountScope(StrEnum):
    ALL = "ALL"
    CATEGORY = "CATEGORY"
    ITEMS = "ITEMS"


class OrderStatus(StrEnum):
    """States of Table 4.6-A in the SRS."""

    PENDING_PAYMENT = "PENDING_PAYMENT"
    ACCEPTED = "ACCEPTED"
    PREPARING = "PREPARING"
    READY = "READY"
    PICKED_UP = "PICKED_UP"
    NO_SHOW = "NO_SHOW"
    CANCELLED = "CANCELLED"
    PAYMENT_FAILED = "PAYMENT_FAILED"


class ModificationStatus(StrEnum):
    HOLDING = "HOLDING"
    APPLIED = "APPLIED"
    RELEASED = "RELEASED"


class PaymentKind(StrEnum):
    AUTH = "AUTH"
    VOID = "VOID"
    REFUND = "REFUND"


class PaymentCause(StrEnum):
    CREATE = "CREATE"
    MODIFY = "MODIFY"
    CANCEL = "CANCEL"
    EXPIRY = "EXPIRY"


class PaymentStatus(StrEnum):
    PENDING = "PENDING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class IdempotencyState(StrEnum):
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
