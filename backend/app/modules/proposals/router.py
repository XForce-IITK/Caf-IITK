import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core import clock
from app.db.session import get_session
from app.models.enums import ProposalStatus
from app.models.identity import User
from app.modules.identity.dependencies import require_permission
from app.modules.identity.permissions import Permission
from app.modules.proposals.schemas import ProposalConflictOut, ProposalDetailOut, RejectRequest
from app.modules.proposals.service import (
    ProposalExpiredError,
    ProposalInvalidatedError,
    ProposalNotFoundError,
    ProposalNotPendingError,
    ProposalService,
)

router = APIRouter(tags=["proposals"])

Admin = Annotated[User, Depends(require_permission(Permission.MANAGE_AGENT))]
DbSession = Annotated[Session, Depends(get_session)]

Responses = dict[int | str, dict[str, Any]]

_NOT_FOUND: Responses = {404: {"description": "No such proposal"}}
_APPROVE_RESPONSES: Responses = _NOT_FOUND | {
    409: {
        "model": ProposalConflictOut,
        "description": "Not applied: already decided, EXPIRED (target start passed or "
        "superseded), or INVALIDATED by re-validation; `detail.proposal` has its status "
        "and reason",
    }
}
_REJECT_RESPONSES: Responses = _NOT_FOUND | {
    409: {
        "model": ProposalConflictOut,
        "description": "Already decided, or EXPIRED; `detail.proposal` has its status",
    },
    422: {"description": "A reason is required"},
}


def _conflict(exc: ProposalNotPendingError) -> HTTPException:
    if isinstance(exc, ProposalExpiredError):
        message = "The proposal has expired"
    elif isinstance(exc, ProposalInvalidatedError):
        message = "The proposal no longer fits the current state and was invalidated"
    else:
        message = "The proposal has already been decided"
    detail = ProposalConflictOut(message=message, proposal=exc.proposal)
    return HTTPException(status.HTTP_409_CONFLICT, detail.model_dump(mode="json"))


@router.get("/admin/proposals")
def list_proposals(
    _admin: Admin, session: DbSession, status: ProposalStatus | None = ProposalStatus.PENDING
) -> list[ProposalDetailOut]:
    """UC-25 step 1: proposals, newest first; PENDING only unless another status is asked for.

    Proposals whose target start has passed, or that a newer one superseded, are
    expired first (FR-56). Each names its run, whose report holds the forecast.
    """
    return ProposalService(session).list_proposals(status, clock.now())


@router.post(
    "/admin/proposals/{proposal_id}/approve",
    responses=_APPROVE_RESPONSES,
)
def approve_proposal(proposal_id: uuid.UUID, admin: Admin, session: DbSession) -> ProposalDetailOut:
    """FR-56, FR-57: re-validate, then apply the change, all in one transaction.

    Item-disable flags the item until the end of the target date (FR-53), prep
    priority orders the slot's kitchen totals (FR-54) and replenishment adds the
    portions (FR-55), under the Administrator's identity with an audit entry that
    links the proposal.
    """
    try:
        return ProposalService(session).approve(admin, proposal_id, clock.now())
    except ProposalNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such proposal") from None
    except ProposalNotPendingError as exc:
        raise _conflict(exc) from None


@router.post(
    "/admin/proposals/{proposal_id}/reject",
    responses=_REJECT_RESPONSES,
)
def reject_proposal(
    proposal_id: uuid.UUID, body: RejectRequest, admin: Admin, session: DbSession
) -> ProposalDetailOut:
    """FR-56: REJECTED with the Administrator's reason; nothing is applied."""
    try:
        return ProposalService(session).reject(admin, proposal_id, body.reason, clock.now())
    except ProposalNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such proposal") from None
    except ProposalNotPendingError as exc:
        raise _conflict(exc) from None
