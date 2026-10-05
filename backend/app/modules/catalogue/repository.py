from datetime import date

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.models.capacity import DailyInventory
from app.models.catalogue import MenuItem
from app.models.enums import ItemCategory, ItemStatus


class MenuItemRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def active_name_exists(self, name: str) -> bool:
        """Case-insensitive, like the uq_menu_items_active_name index."""
        return (
            self.session.scalar(
                select(MenuItem.id).where(
                    func.lower(MenuItem.name) == name.lower(),
                    MenuItem.status == ItemStatus.ACTIVE,
                )
            )
            is not None
        )

    def add(
        self, *, name: str, description: str, category: ItemCategory, price_paise: int
    ) -> MenuItem:
        item = MenuItem(
            name=name, description=description, category=category, price_paise=price_paise
        )
        self.session.add(item)
        self.session.flush()
        self.session.refresh(item)  # load server defaults (status, unavailable)
        return item

    def list_active_with_available(self, service_date: date) -> list[tuple[MenuItem, int]]:
        """ACTIVE items with their available portions for the date (0 if none were set)."""
        available = func.coalesce(DailyInventory.total - DailyInventory.allocated, 0)
        rows = self.session.execute(
            select(MenuItem, available)
            .outerjoin(
                DailyInventory,
                and_(
                    DailyInventory.item_id == MenuItem.id,
                    DailyInventory.service_date == service_date,
                ),
            )
            .where(MenuItem.status == ItemStatus.ACTIVE)
            .order_by(MenuItem.category, func.lower(MenuItem.name))
        )
        return [(item, portions) for item, portions in rows]
