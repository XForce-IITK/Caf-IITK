"""Discount rules (FR-22 / US-17): the Administrator creates, edits and deactivates them.

A rule covers a slot whose start time is in [start_time, end_time): a rule ending
at 12:30 does not discount the 12:30 slot (E28; see `engine.DiscountRule.covers`).
Rules are not tied to a service date, so "within the service window" is checked
as a range within one day; on a date whose window it misses, a rule covers no slot.

A change reaches only quotes and orders priced after it commits: every order
keeps its price snapshot (FR-27). Every change is audited (FR-47).
"""

import uuid
from dataclasses import asdict, dataclass, replace
from datetime import time

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.catalogue import DiscountRule, DiscountRuleItem
from app.models.enums import DiscountScope, ItemCategory
from app.models.identity import User
from app.modules.audit.service import write_audit
from app.modules.pricing.repository import PricingRepository
from app.modules.pricing.schemas import DiscountRuleCreate, DiscountRuleOut, DiscountRuleUpdate


class DiscountRuleNotFoundError(Exception):
    pass


class InvalidRuleError(Exception):
    """The fields do not fit together; each problem names the field to correct."""

    def __init__(self, problems: list[tuple[str, str]]) -> None:
        super().__init__("; ".join(message for _, message in problems))
        self.problems = problems


@dataclass(frozen=True)
class _Rule:
    """The editable fields of a rule, as validated and audited together."""

    name: str
    start_time: time
    end_time: time
    pct: int
    scope: DiscountScope
    category: ItemCategory | None
    item_ids: frozenset[uuid.UUID]
    active: bool = True

    def audit(self) -> dict[str, object]:
        values = asdict(self)
        values.update(
            start_time=self.start_time.isoformat(),
            end_time=self.end_time.isoformat(),
            scope=self.scope.value,
            category=self.category.value if self.category else None,
            item_ids=sorted(str(i) for i in self.item_ids),
        )
        return values


def _scope_problems(rule: _Rule) -> list[tuple[str, str]]:
    needs_category = rule.scope is DiscountScope.CATEGORY
    needs_items = rule.scope is DiscountScope.ITEMS
    problems = []
    if needs_category and rule.category is None:
        problems.append(("category", "a CATEGORY rule needs a category"))
    if not needs_category and rule.category is not None:
        problems.append(("category", f"a {rule.scope.value} rule takes no category"))
    if needs_items and not rule.item_ids:
        problems.append(("item_ids", "an ITEMS rule needs at least one item"))
    if not needs_items and rule.item_ids:
        problems.append(("item_ids", f"a {rule.scope.value} rule takes no item_ids"))
    return problems


class DiscountRuleService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repo = PricingRepository(session)

    def list_rules(self) -> list[DiscountRuleOut]:
        with self.session.begin():
            rows = self.session.scalars(
                select(DiscountRule).order_by(
                    DiscountRule.start_time, DiscountRule.name, DiscountRule.id
                )
            ).all()
            items = self._item_ids([row.id for row in rows])
            return [_out(row, items.get(row.id, frozenset())) for row in rows]

    def create(self, admin: User, request: DiscountRuleCreate) -> DiscountRuleOut:
        rule = _Rule(
            name=request.name,
            start_time=request.start_time,
            end_time=request.end_time,
            pct=request.pct,
            scope=request.scope,
            category=request.category,
            item_ids=frozenset(request.item_ids),
        )
        with self.session.begin():
            self._check(rule, new_items=rule.item_ids)
            row = DiscountRule(
                name=rule.name,
                start_time=rule.start_time,
                end_time=rule.end_time,
                pct=rule.pct,
                scope=rule.scope,
                category=rule.category,
                active=True,
            )
            self.session.add(row)
            self.session.flush()
            self._set_items(row.id, rule.item_ids)
            write_audit(
                self.session,
                action="DISCOUNT_RULE_CREATED",
                entity_type="discount_rule",
                entity_id=str(row.id),
                actor_id=str(admin.id),
                actor_role=admin.role.value,
                after=rule.audit(),
            )
            self.session.refresh(row)  # created_at
            return _out(row, rule.item_ids)

    def update(
        self, admin: User, rule_id: uuid.UUID, request: DiscountRuleUpdate
    ) -> DiscountRuleOut:
        """Only the fields that actually change are audited; no change writes nothing."""
        with self.session.begin():
            row = self.session.scalars(
                select(DiscountRule)
                .where(DiscountRule.id == rule_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            ).one_or_none()
            if row is None:
                raise DiscountRuleNotFoundError
            current = _Rule(
                name=row.name,
                start_time=row.start_time,
                end_time=row.end_time,
                pct=row.pct,
                scope=row.scope,
                category=row.category,
                item_ids=self._item_ids([row.id]).get(row.id, frozenset()),
                active=row.active,
            )
            changes: dict[str, object] = {
                field: getattr(request, field) for field in request.model_fields_set
            }
            if "item_ids" in changes:
                changes["item_ids"] = frozenset(request.item_ids or ())
            if "scope" in changes:
                # The old scope's category or items do not carry over to a new scope.
                changes.setdefault("category", None)
                changes.setdefault("item_ids", frozenset())
            updated = replace(current, **changes)  # type: ignore[arg-type]
            self._check(updated, new_items=updated.item_ids - current.item_ids)

            before, after = current.audit(), updated.audit()
            changed = sorted(field for field in after if after[field] != before[field])
            if changed:
                for field in ("name", "start_time", "end_time", "pct", "scope", "category"):
                    setattr(row, field, getattr(updated, field))
                row.active = updated.active
                if updated.item_ids != current.item_ids:
                    self._set_items(row.id, updated.item_ids)
                write_audit(
                    self.session,
                    action="DISCOUNT_RULE_UPDATED",
                    entity_type="discount_rule",
                    entity_id=str(row.id),
                    actor_id=str(admin.id),
                    actor_role=admin.role.value,
                    before={field: before[field] for field in changed},
                    after={field: after[field] for field in changed},
                )
            return _out(row, updated.item_ids)

    def _check(self, rule: _Rule, *, new_items: frozenset[uuid.UUID]) -> None:
        problems = []
        if rule.start_time >= rule.end_time:
            problems.append(("end_time", "end_time must be after start_time"))
        problems += _scope_problems(rule)
        # Items already on the rule may since have been removed; only added ones are checked.
        if new_items:
            active = self.repo.get_active_items(sorted(new_items))
            missing = sorted(str(i) for i in new_items if i not in active)
            if missing:
                problems.append(("item_ids", f"unknown or removed items: {', '.join(missing)}"))
        if problems:
            raise InvalidRuleError(problems)

    def _item_ids(self, rule_ids: list[uuid.UUID]) -> dict[uuid.UUID, frozenset[uuid.UUID]]:
        found: dict[uuid.UUID, set[uuid.UUID]] = {}
        if rule_ids:
            links = self.session.execute(
                select(DiscountRuleItem.rule_id, DiscountRuleItem.item_id).where(
                    DiscountRuleItem.rule_id.in_(rule_ids)
                )
            )
            for rule_id, item_id in links:
                found.setdefault(rule_id, set()).add(item_id)
        return {rule_id: frozenset(ids) for rule_id, ids in found.items()}

    def _set_items(self, rule_id: uuid.UUID, item_ids: frozenset[uuid.UUID]) -> None:
        self.session.execute(delete(DiscountRuleItem).where(DiscountRuleItem.rule_id == rule_id))
        self.session.add_all(
            DiscountRuleItem(rule_id=rule_id, item_id=item_id) for item_id in sorted(item_ids)
        )
        self.session.flush()


def _out(row: DiscountRule, item_ids: frozenset[uuid.UUID]) -> DiscountRuleOut:
    return DiscountRuleOut(
        id=row.id,
        name=row.name,
        start_time=row.start_time,
        end_time=row.end_time,
        pct=row.pct,
        scope=row.scope,
        category=row.category,
        item_ids=sorted(item_ids),
        active=row.active,
        created_at=row.created_at,
    )
