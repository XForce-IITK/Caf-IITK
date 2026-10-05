import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models.capacity import DailyInventory, ServiceDay
from app.models.catalogue import MenuItem


class InventoryRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_item(self, item_id: uuid.UUID) -> MenuItem | None:
        return self.session.get(MenuItem, item_id)

    def service_day_exists(self, service_date: date) -> bool:
        return self.session.get(ServiceDay, service_date) is not None

    def lock_or_create(self, item_id: uuid.UUID, service_date: date) -> tuple[DailyInventory, bool]:
        """Return the row locked FOR UPDATE, creating it with total 0 if absent.

        Returns (row, created). ON CONFLICT DO NOTHING lets two concurrent first-time
        sets both proceed: one inserts, and both then serialise on the row lock.
        """
        inserted = self.session.execute(
            insert(DailyInventory)
            .values(item_id=item_id, service_date=service_date, total=0, allocated=0)
            .on_conflict_do_nothing()
            .returning(DailyInventory.item_id)
        ).first()
        row = self.session.scalars(
            select(DailyInventory)
            .where(DailyInventory.item_id == item_id, DailyInventory.service_date == service_date)
            .with_for_update()
            .execution_options(populate_existing=True)
        ).one()
        return row, inserted is not None
