"""Proposal decisions (UC-25, UC-26; FR-53 - FR-57).

A proposal changes anything only here, on an Administrator's approval, under that
Administrator's identity: re-validated against the current state, then applied in
the same transaction that marks it APPROVED and writes the audit entry.
"""

import uuid
from datetime import datetime, time, timedelta

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core import clock
from app.models.agent import Proposal
from app.models.enums import ItemStatus, ProposalStatus, ProposalType
from app.models.identity import User
from app.modules.audit.service import write_audit
from app.modules.catalogue.repository import MenuItemRepository
from app.modules.catalogue.service import flag_state
from app.modules.proposals.payloads import (
    DisablePayload,
    PrepPriorityPayload,
    ReplenishPayload,
    parse_payload,
)
from app.modules.proposals.repository import ProposalRepository
from app.modules.proposals.schemas import ProposalDetailOut

# The daily_inventory.total CHECK constraint's upper bound (FR-14).
MAX_PORTIONS = 500


class ProposalNotFoundError(Exception):
    pass


class ProposalNotPendingError(Exception):
    """Already decided, expired or invalidated: only a PENDING proposal can be decided."""

    def __init__(self, proposal: ProposalDetailOut) -> None:
        self.proposal = proposal


class ProposalExpiredError(ProposalNotPendingError):
    """Its target start has passed, or a newer proposal superseded it; it is now EXPIRED."""


class ProposalInvalidatedError(ProposalNotPendingError):
    """Re-validation failed (FR-57); it is now INVALIDATED and nothing changed."""


class _Invalid(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason


def _detail(proposal: Proposal) -> ProposalDetailOut:
    return ProposalDetailOut.model_validate(proposal)


class ProposalService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repo = ProposalRepository(session)

    def list_proposals(
        self, status: ProposalStatus | None, now: datetime
    ) -> list[ProposalDetailOut]:
        """Proposals, newest first; stale PENDING ones are expired first, so none is shown
        as decidable after its target start."""
        with self.session.begin():
            self._expire(now)
            return [_detail(p) for p in self.repo.find(status)]

    def expire_stale(self, now: datetime) -> int:
        """UC-26: the worker's periodic expiry. Returns how many proposals expired."""
        with self.session.begin():
            return self._expire(now)

    def approve(self, admin: User, proposal_id: uuid.UUID, now: datetime) -> ProposalDetailOut:
        """UC-25: re-validate, then apply, mark APPROVED and audit, all in one transaction.

        Raises ProposalExpiredError or ProposalInvalidatedError after committing the
        new status, so the caller can answer 409 with it.
        """
        with self.session.begin():
            proposal = self._lock_pending(proposal_id, now)
            if proposal.status is ProposalStatus.PENDING:
                try:
                    # A savepoint, so a failed re-validation leaves nothing half-applied.
                    with self.session.begin_nested():
                        self._apply(admin, proposal, now)
                except _Invalid as exc:
                    self._decide(proposal, ProposalStatus.INVALIDATED, admin, now, exc.reason)
                else:
                    self._decide(proposal, ProposalStatus.APPROVED, admin, now, None)
            result = _detail(proposal)
        if result.status is ProposalStatus.EXPIRED:
            raise ProposalExpiredError(result)
        if result.status is ProposalStatus.INVALIDATED:
            raise ProposalInvalidatedError(result)
        return result

    def reject(
        self, admin: User, proposal_id: uuid.UUID, reason: str, now: datetime
    ) -> ProposalDetailOut:
        """UC-25 2a: REJECTED with the reason; nothing is applied."""
        with self.session.begin():
            proposal = self._lock_pending(proposal_id, now)
            if proposal.status is ProposalStatus.PENDING:
                self._decide(proposal, ProposalStatus.REJECTED, admin, now, reason)
            result = _detail(proposal)
        if result.status is ProposalStatus.EXPIRED:
            raise ProposalExpiredError(result)
        return result

    def _expire(self, now: datetime) -> int:
        expired = self.repo.expire_stale(now)
        for proposal_id in expired:
            write_audit(
                self.session,
                action="PROPOSAL_EXPIRED",
                entity_type="proposal",
                entity_id=str(proposal_id),
                actor_role="SYSTEM",
                after={"status": ProposalStatus.EXPIRED.value},
                correlation_id=str(proposal_id),
            )
        return len(expired)

    def _lock_pending(self, proposal_id: uuid.UUID, now: datetime) -> Proposal:
        """The proposal, locked; still PENDING, or just set EXPIRED if its time has passed.

        Concurrent decisions serialise on the lock, so the second one finds the
        proposal decided and gets ProposalNotPendingError (UC-25 2c).
        """
        proposal = self.repo.lock(proposal_id)
        if proposal is None:
            raise ProposalNotFoundError
        if proposal.status is not ProposalStatus.PENDING:
            raise ProposalNotPendingError(_detail(proposal))
        if now >= proposal.expires_at or self.repo.is_superseded(proposal.id):
            self._decide(proposal, ProposalStatus.EXPIRED, None, now, None)
        return proposal

    def _decide(
        self,
        proposal: Proposal,
        status: ProposalStatus,
        admin: User | None,
        now: datetime,
        reason: str | None,
    ) -> None:
        before = {"status": proposal.status.value}
        proposal.status = status
        proposal.decided_by = admin.id if admin else None
        proposal.decided_at = now
        proposal.decision_reason = reason
        proposal.version += 1
        write_audit(
            self.session,
            action=f"PROPOSAL_{status.value}",
            entity_type="proposal",
            entity_id=str(proposal.id),
            actor_id=str(admin.id) if admin else None,
            actor_role=admin.role.value if admin else "SYSTEM",
            before=before,
            after={"status": status.value, "reason": reason},
            correlation_id=str(proposal.id),
        )

    def _apply(self, admin: User, proposal: Proposal, now: datetime) -> None:
        """FR-57: check the proposal against the current state and apply it, or raise _Invalid."""
        if proposal.target_date < now.date():
            raise _Invalid("The target service date has passed")
        try:
            payload = parse_payload(proposal.type, proposal.payload)
        except ValidationError:
            raise _Invalid("The proposal's content is malformed") from None
        if isinstance(payload, DisablePayload):
            self._apply_disable(admin, proposal, payload)
        elif isinstance(payload, ReplenishPayload):
            self._apply_replenish(admin, proposal, payload)
        else:
            assert proposal.type is ProposalType.PREP_PRIORITY
            self._apply_prep_priority(admin, proposal, payload)

    def _check_active(self, item_ids: list[uuid.UUID]) -> None:
        items = self.repo.items(item_ids)
        gone = [i for i in item_ids if i not in items or items[i].status is not ItemStatus.ACTIVE]
        if gone:
            raise _Invalid(f"Items no longer on the menu: {', '.join(map(str, gone))}")

    def _apply_disable(self, admin: User, proposal: Proposal, payload: DisablePayload) -> None:
        """FR-53: flag the item unavailable until the end of the target service date."""
        item = MenuItemRepository(self.session).lock(payload.item_id)
        if item is None or item.status is not ItemStatus.ACTIVE:
            raise _Invalid(f"Item no longer on the menu: {payload.item_id}")
        before = flag_state(item)
        item.unavailable = True
        item.unavailable_reason = payload.reason
        item.unavailable_source = str(proposal.id)
        item.unavailable_until = datetime.combine(
            proposal.target_date + timedelta(days=1), time.min, tzinfo=clock.IST
        )
        self._audit_change(
            admin, proposal, "ITEM_FLAGGED", "menu_item", str(item.id), before, flag_state(item)
        )

    def _apply_replenish(self, admin: User, proposal: Proposal, payload: ReplenishPayload) -> None:
        """FR-55: add the portions to the target date's inventory."""
        item_ids = [line.item_id for line in payload.lines]
        self._check_active(item_ids)
        limit = int(self.repo.get_setting("P-REPL_MAX"))
        over = [str(line.item_id) for line in payload.lines if line.additional_portions > limit]
        if over:
            raise _Invalid(f"More than P-REPL_MAX ({limit}) additional portions: {', '.join(over)}")
        if not self.repo.service_day_exists(proposal.target_date):
            raise _Invalid("The target service day is not configured")
        rows = self.repo.lock_inventory(item_ids, proposal.target_date)
        for line in sorted(payload.lines, key=lambda line: line.item_id):
            row = rows.get(line.item_id)
            before: dict[str, object] | None = (
                {"total": row.total, "allocated": row.allocated} if row else None
            )
            new_total = (row.total if row else 0) + line.additional_portions
            if new_total > MAX_PORTIONS:
                raise _Invalid(f"Inventory for {line.item_id} would exceed {MAX_PORTIONS} portions")
            if row is None:
                row = self.repo.add_inventory(line.item_id, proposal.target_date, new_total)
            else:
                row.total = new_total
            self._audit_change(
                admin,
                proposal,
                "INVENTORY_REPLENISHED",
                "daily_inventory",
                f"{line.item_id}:{proposal.target_date.isoformat()}",
                before,
                {"total": row.total, "allocated": row.allocated},
            )

    def _apply_prep_priority(
        self, admin: User, proposal: Proposal, payload: PrepPriorityPayload
    ) -> None:
        """FR-54: the approved list becomes the slot's prep order in the kitchen queue."""
        if proposal.target_slot_id is None or self.repo.get_slot(proposal.target_slot_id) is None:
            raise _Invalid("The target slot no longer exists")
        self._check_active(payload.item_ids)
        pending = self.repo.pending_item_ids(proposal.target_slot_id)
        idle = [str(i) for i in payload.item_ids if i not in pending]
        if idle:
            raise _Invalid(f"Items with no pending orders in the slot: {', '.join(idle)}")
        self._audit_change(
            admin,
            proposal,
            "PREP_PRIORITY_SET",
            "slot",
            str(proposal.target_slot_id),
            None,
            {"item_ids": [str(i) for i in payload.item_ids]},
        )

    def _audit_change(
        self,
        admin: User,
        proposal: Proposal,
        action: str,
        entity_type: str,
        entity_id: str,
        before: dict[str, object] | None,
        after: dict[str, object],
    ) -> None:
        """The change itself, under the Administrator's identity, linked to the proposal."""
        write_audit(
            self.session,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            actor_id=str(admin.id),
            actor_role=admin.role.value,
            before=before,
            after=after | {"proposal_id": str(proposal.id)},
            correlation_id=str(proposal.id),
        )
