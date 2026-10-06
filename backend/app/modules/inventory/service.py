import uuid
from datetime import date

from sqlalchemy.orm import Session

from app.models.capacity import DailyInventory
from app.models.enums import ItemStatus
from app.models.identity import User
from app.modules.audit.service import write_audit
from app.modules.inventory.repository import InventoryRepository


class ItemNotFoundError(Exception):
    pass


class ItemNotActiveError(Exception):
    pass


class ServiceDayNotConfiguredError(Exception):
    pass


class BelowAllocatedError(Exception):
    """The new total would make available portions negative (FR-15)."""

    def __init__(self, allocated: int) -> None:
        self.allocated = allocated


class InventoryService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.inventory = InventoryRepository(session)

    def set_total(
        self, admin: User, item_id: uuid.UUID, service_date: date, total: int
    ) -> DailyInventory:
        """FR-14 / US-11: set, replenish or reduce an item's portions for a service date.

        The row is locked so a concurrent order allocation cannot slip between the
        check and the update; a total below `allocated` is refused and nothing changes
        (FR-15). The CHECK constraint backs this up at the database level.
        """
        with self.session.begin():
            item = self.inventory.get_item(item_id)
            if item is None:
                raise ItemNotFoundError
            if item.status != ItemStatus.ACTIVE:
                raise ItemNotActiveError
            if not self.inventory.service_day_exists(service_date):
                raise ServiceDayNotConfiguredError
            row, created = self.inventory.lock_or_create(item_id, service_date)
            if total < row.allocated:
                raise BelowAllocatedError(row.allocated)
            before = None if created else {"total": row.total, "allocated": row.allocated}
            row.total = total
            write_audit(
                self.session,
                action="INVENTORY_SET",
                entity_type="daily_inventory",
                entity_id=f"{item_id}:{service_date.isoformat()}",
                actor_id=str(admin.id),
                actor_role=admin.role.value,
                before=before,
                after={"total": row.total, "allocated": row.allocated},
            )
            return row
