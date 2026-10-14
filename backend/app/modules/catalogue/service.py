import uuid
from datetime import date, datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.catalogue import MenuItem
from app.models.enums import ItemStatus
from app.models.identity import User
from app.modules.audit.service import write_audit
from app.modules.catalogue.domain import not_orderable_reason
from app.modules.catalogue.repository import MenuItemRepository
from app.modules.catalogue.schemas import ItemCreate, MenuItemOut, MenuOut

# unavailable_source for a flag set by Kitchen Staff or the Administrator by hand,
# as opposed to one set by approving an item-disable proposal (FR-53).
STAFF_FLAG_SOURCE = "STAFF"


class DuplicateItemNameError(Exception):
    """Another ACTIVE item already has this name (case-insensitive)."""


class ItemNotFoundError(Exception):
    pass


class ItemNotActiveError(Exception):
    """Only an ACTIVE item can be flagged or unflagged (FR-11)."""


def _flag_state(item: MenuItem) -> dict[str, object]:
    return {
        "unavailable": item.unavailable,
        "reason": item.unavailable_reason,
        "source": item.unavailable_source,
        "until": item.unavailable_until.isoformat() if item.unavailable_until else None,
    }


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

    def flag_item(self, staff: User, item_id: uuid.UUID, reason: str) -> MenuItem:
        """FR-11 / US-09: make an ACTIVE item non-orderable until the flag is cleared.

        Only the flag columns change: portions, prices and orders already placed are
        untouched. Flagging an already flagged item replaces its reason.
        """
        with self.session.begin():
            item = self._lock_active(item_id)
            before = _flag_state(item)
            item.unavailable = True
            item.unavailable_reason = reason
            item.unavailable_source = STAFF_FLAG_SOURCE
            item.unavailable_until = None
            self._audit_flag(staff, item, "ITEM_FLAGGED", before)
            return item

    def clear_flag(self, staff: User, item_id: uuid.UUID) -> MenuItem:
        """FR-11 / US-09: make a flagged item orderable again. Clearing twice is a no-op."""
        with self.session.begin():
            item = self._lock_active(item_id)
            if not item.unavailable:
                return item
            before = _flag_state(item)
            item.unavailable = False
            item.unavailable_reason = None
            item.unavailable_source = None
            item.unavailable_until = None
            self._audit_flag(staff, item, "ITEM_UNFLAGGED", before)
            return item

    def _lock_active(self, item_id: uuid.UUID) -> MenuItem:
        item = self.items.lock(item_id)
        if item is None:
            raise ItemNotFoundError
        if item.status is not ItemStatus.ACTIVE:
            raise ItemNotActiveError
        return item

    def _audit_flag(
        self, staff: User, item: MenuItem, action: str, before: dict[str, object]
    ) -> None:
        write_audit(
            self.session,
            action=action,
            entity_type="menu_item",
            entity_id=str(item.id),
            actor_id=str(staff.id),
            actor_role=staff.role.value,
            before=before,
            after=_flag_state(item),
        )

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
