import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core import clock
from app.db.session import get_session
from app.models.enums import AgentTrigger
from app.models.identity import User
from app.modules.agent.repository import RunInProgressError, RunRepository
from app.modules.agent.schemas import (
    AgentRunDetailOut,
    AgentRunOut,
    ProposalOut,
    RunInProgressOut,
    ToolCallOut,
)
from app.modules.agent.service import AgentService
from app.modules.identity.dependencies import require_permission
from app.modules.identity.permissions import Permission

router = APIRouter(tags=["agent"])

Admin = Annotated[User, Depends(require_permission(Permission.MANAGE_AGENT))]
DbSession = Annotated[Session, Depends(get_session)]

# How many runs the history lists.
HISTORY_LIMIT = 20


@router.post(
    "/admin/agent/runs",
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        403: {"description": "Only the Administrator triggers planning runs"},
        409: {"description": "A run is already in progress; `detail.running_run_id` names it"},
    },
)
def trigger_agent_run(admin: Admin, session: DbSession) -> AgentRunOut:
    """FR-50: queue an on-demand planning run; caf-worker executes it within seconds.

    Only one run is in progress at a time: while one is QUEUED or RUNNING this
    answers 409 with that run's ID.
    """
    try:
        run = AgentService(session).request_run(AgentTrigger.ON_DEMAND, admin.id, clock.now())
    except RunInProgressError as exc:
        detail = RunInProgressOut(
            message="A planning run is already in progress", running_run_id=exc.run_id
        )
        raise HTTPException(status.HTTP_409_CONFLICT, detail.model_dump(mode="json")) from exc
    return AgentRunOut.model_validate(run)


@router.get("/admin/agent/runs")
def list_agent_runs(_admin: Admin, session: DbSession) -> list[AgentRunOut]:
    """FR-63: run history, newest first."""
    return [AgentRunOut.model_validate(r) for r in RunRepository(session).recent(HISTORY_LIMIT)]


@router.get("/admin/agent/runs/{run_id}", responses={404: {"description": "No such run"}})
def get_agent_run(run_id: uuid.UUID, _admin: Admin, session: DbSession) -> AgentRunDetailOut:
    """FR-63: one run with its report, proposals and tool-call log."""
    runs = RunRepository(session)
    run = runs.get(run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such run")
    return AgentRunDetailOut(
        **AgentRunOut.model_validate(run).model_dump(),
        report=run.report,
        proposals=[ProposalOut.model_validate(p) for p in runs.proposals_of(run_id)],
        tool_calls=[ToolCallOut(**c) for c in runs.tool_calls_of(run_id)],
    )
