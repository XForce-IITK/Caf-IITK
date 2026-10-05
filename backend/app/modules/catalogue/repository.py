from sqlalchemy import func, select
from sqlalchemy.orm import Session

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
