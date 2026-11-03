"""Audit writer (FR-47 - FR-49).

Business changes are audited inside the transaction that makes the change: call
`write_audit` with the session that is about to commit. Security events
(rejected requests) have no business transaction, so `record_security_event`
commits its own.
"""

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.core import context
from app.core.logs import redact_value
from app.models.platform import AuditLog
from app.modules.audit.repository import AuditRepository
from app.modules.audit.schemas import AuditEntryOut, AuditPageOut

# FR-49: how many entries one page of a search returns at most.
MAX_AUDIT_PAGE = 200


def write_audit(
    session: Session,
    *,
    action: str,
    entity_type: str,
    entity_id: str | None = None,
    actor_id: str | None = None,
    actor_role: str | None = None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    correlation_id: str | None = None,
) -> None:
    session.add(
        AuditLog(
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            actor_id=actor_id,
            actor_role=actor_role,
            before=before,
            after=after,
            # NFR-29: the request's (or worker job's) correlation ID unless one is given.
            correlation_id=correlation_id or context.correlation_id(),
        )
    )


def record_security_event(
    session: Session,
    *,
    action: str,
    actor_id: str | None,
    actor_role: str | None,
    details: dict[str, Any],
) -> None:
    with session.begin():
        write_audit(
            session,
            action=action,
            entity_type="security",
            actor_id=actor_id,
            actor_role=actor_role,
            after=details,
        )


def _redacted(values: dict[str, Any] | None) -> dict[str, Any] | None:
    if values is None:
        return None
    return {key: redact_value(key, value) for key, value in values.items()}


class AuditService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repo = AuditRepository(session)

    def search(
        self,
        *,
        since: datetime | None = None,
        until: datetime | None = None,
        actor_id: str | None = None,
        entity_type: str | None = None,
        entity_id: str | None = None,
        action: str | None = None,
        before_id: int | None = None,
        limit: int = 50,
    ) -> AuditPageOut:
        """FR-49: one page of matching entries, newest first.

        Nothing writes a secret into the log, and before/after values are redacted
        again here, by key and by content, so a mistake elsewhere cannot leak one.
        """
        with self.session.begin():
            rows = self.repo.search(
                since=since,
                until=until,
                actor_id=actor_id,
                entity_type=entity_type,
                entity_id=entity_id,
                action=action,
                before_id=before_id,
                # One more than asked, to know whether there is another page.
                limit=limit + 1,
            )
        page = rows[:limit]
        return AuditPageOut(
            entries=[
                AuditEntryOut(
                    id=row.id,
                    at=row.at,
                    actor_id=row.actor_id,
                    actor_role=row.actor_role,
                    action=row.action,
                    entity_type=row.entity_type,
                    entity_id=row.entity_id,
                    before=_redacted(row.before),
                    after=_redacted(row.after),
                    correlation_id=row.correlation_id,
                )
                for row in page
            ],
            next_before_id=page[-1].id if len(rows) > limit else None,
        )
