"""The proposals' caf-worker job: expire stale proposals (UC-26, FR-56)."""

from app.core import clock
from app.db.session import get_sessionmaker
from app.modules.proposals.service import ProposalService
from app.worker.jobs import Job

EXPIRY_CHECK_S = 60


def expire_proposals() -> None:
    with get_sessionmaker()() as session:
        ProposalService(session).expire_stale(clock.now())


PROPOSAL_JOBS = [Job("proposal-expiry", expire_proposals, EXPIRY_CHECK_S)]
