"""Liveness, readiness and metrics (NFR-31), outside /api/v1.

Docker uses /ready as caf-api's health check, so a container counts as healthy only
while it can reach the database. These endpoints serve Docker and Prometheus, not
the client, so /ready and /metrics stay out of the OpenAPI schema.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core import metrics
from app.core.errors import DATABASE_RETRY_AFTER_S
from app.db.session import get_session
from app.modules.agent.repository import RunRepository

router = APIRouter(tags=["ops"])


# Liveness: the process is up and answering. (A docstring would change the client.)
@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready", include_in_schema=False)
def ready(session: Annotated[Session, Depends(get_session)]) -> JSONResponse:
    """Readiness: 200 once the database answers, else 503 with Retry-After (NFR-16)."""
    try:
        session.execute(text("SELECT 1"))
    except SQLAlchemyError:
        return JSONResponse(
            {"status": "unavailable"},
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            headers={"Retry-After": str(DATABASE_RETRY_AFTER_S)},
        )
    return JSONResponse({"status": "ready"})


@router.get("/metrics", include_in_schema=False)
def prometheus_metrics(session: Annotated[Session, Depends(get_session)]) -> Response:
    """Prometheus text format. Still answers while the database is down, with
    caf_database_up 0, since that is when the request metrics matter most.
    """
    try:
        agent_runs = RunRepository(session).count_by_status_and_source()
    except SQLAlchemyError:
        agent_runs = None
    return Response(
        metrics.render(metrics.database_families(agent_runs)),
        media_type=metrics.CONTENT_TYPE_LATEST,
    )
