from datetime import date, datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.catalogue import MenuItem
from app.models.identity import User
from app.modules.audit.service import write_audit
from app.modules.catalogue.domain import not_orderable_reason
from app.modules.catalogue.repository import MenuItemRepository
from app.modules.catalogue.schemas import ItemCreate, MenuItemOut, MenuOut


class DuplicateItemNameError(Exception):
    """Another ACTIVE item already has this name (case-insensitive)."""


class CatalogueService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.items = MenuItemRepository(session)

    def onboard_item(self, admin: User, request: ItemCreate) -> MenuItem:
        """FR-8 / US-06: a new item is ACTIVE; the change is audited in the same transaction."""
        try:
            with self.session.begin():
                if self.items.active_name_exists(request.name):
                    raise DuplicateItemNameError
                item = self.items.add(
                    name=request.name,
                    description=request.description,
                    category=request.category,
                    price_paise=request.price_paise,
                )
                write_audit(
                    self.session,
                    action="ITEM_CREATED",
                    entity_type="menu_item",
                    entity_id=str(item.id),
                    actor_id=str(admin.id),
                    actor_role=admin.role.value,
                    after={
                        "name": item.name,
                        "category": item.category.value,
                        "price_paise": item.price_paise,
                        "status": item.status.value,
                    },
                )
                return item
        except IntegrityError as exc:
            # A concurrent request created the same name between the check and the insert;
            # the partial unique index uq_menu_items_active_name caught it.
            raise DuplicateItemNameError from exc

    def browse_menu(self, service_date: date, now: datetime) -> MenuOut:
        """FR-13 / US-10: every ACTIVE item with its available portions and orderability."""
        with self.session.begin():
            rows = self.items.list_active_with_available(service_date)
        items = []
        for item, available in rows:
            reason = not_orderable_reason(
                status=item.status,
                unavailable=item.unavailable,
                unavailable_until=item.unavailable_until,
                available=available,
                now=now,
            )
            items.append(
                MenuItemOut(
                    id=item.id,
                    name=item.name,
                    description=item.description,
                    category=item.category,
                    price_paise=item.price_paise,
                    available_portions=available,
                    orderable=reason is None,
                    not_orderable_reason=reason,
                )
            )
        return MenuOut(service_date=service_date, items=items)
