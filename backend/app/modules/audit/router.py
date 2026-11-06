from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.text import NulFreeStr
from app.db.session import get_session
from app.models.identity import User
from app.modules.audit.schemas import AuditPageOut
from app.modules.audit.service import MAX_AUDIT_PAGE, AuditService
from app.modules.identity.dependencies import require_permission
from app.modules.identity.permissions import Permission

router = APIRouter(tags=["audit"])

MAX_BIGINT = 2**63 - 1

Text = Annotated[NulFreeStr | None, Query(min_length=1, max_length=64)]


@router.get(
    "/admin/audit",
    responses={
        403: {"description": "Only the Administrator searches the audit log"},
        422: {"description": "Invalid filter, or `from` is not before `to`"},
    },
)
def search_audit(
    admin: Annotated[User, Depends(require_permission(Permission.VIEW_ALL))],
    session: Annotated[Session, Depends(get_session)],
    since: Annotated[datetime | None, Query(alias="from", description="Inclusive.")] = None,
    until: Annotated[datetime | None, Query(alias="to", description="Exclusive.")] = None,
    actor_id: Text = None,
    entity_type: Text = None,
    entity_id: Annotated[
        NulFreeStr | None,
        Query(
            min_length=1,
            max_length=64,
            description="Also matches entries that name this ID as their order.",
        ),
    ] = None,
    action: Text = None,
    before_id: Annotated[
        int | None,
        # audit_log.id is a bigint; a larger value would fail inside the query.
        Query(ge=1, le=MAX_BIGINT, description="next_before_id of the previous page."),
    ] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_AUDIT_PAGE)] = 50,
) -> AuditPageOut:
    """FR-49 / US-38: search the append-only audit log by time range, actor, entity
    and action, newest first, a page at a time. Secrets never appear in results."""
    if since is not None and until is not None and since >= until:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "`from` must be before `to`")
    return AuditService(session).search(
        since=since,
        until=until,
        actor_id=actor_id,
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        before_id=before_id,
        limit=limit,
    )
