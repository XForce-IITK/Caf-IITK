"""Audit writer (FR-47 - FR-49).

Business changes are audited inside the transaction that makes the change: call
`write_audit` with the session that is about to commit. Security events
(rejected requests) have no business transaction, so `record_security_event`
commits its own.
"""

from typing import Any

from sqlalchemy.orm import Session

from app.models.platform import AuditLog


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
            correlation_id=correlation_id,
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
