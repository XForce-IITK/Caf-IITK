from datetime import datetime

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.models.platform import AuditLog


class AuditRepository:
    """Reads only: the application's role cannot change an entry (NFR-26)."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def search(
        self,
        *,
        since: datetime | None,
        until: datetime | None,
        actor_id: str | None,
        entity_type: str | None,
        entity_id: str | None,
        action: str | None,
        before_id: int | None,
        limit: int,
    ) -> list[AuditLog]:
        """Matching entries, newest first. `entity_id` also matches entries that name it
        as their order (a portion or seat change, or a security event about it)."""
        query: Select[tuple[AuditLog]] = select(AuditLog)
        if since is not None:
            query = query.where(AuditLog.at >= since)
        if until is not None:
            query = query.where(AuditLog.at < until)
        if actor_id is not None:
            query = query.where(AuditLog.actor_id == actor_id)
        if entity_type is not None:
            query = query.where(AuditLog.entity_type == entity_type)
        if entity_id is not None:
            query = query.where(
                (AuditLog.entity_id == entity_id) | (AuditLog.after["order_id"].astext == entity_id)
            )
        if action is not None:
            query = query.where(AuditLog.action == action)
        if before_id is not None:
            query = query.where(AuditLog.id < before_id)
        return list(self.session.scalars(query.order_by(AuditLog.id.desc()).limit(limit)))
