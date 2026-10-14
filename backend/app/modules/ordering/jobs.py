"""The ordering module's caf-worker jobs."""

from app.core import clock as clock
from app.db.session import get_sessionmaker
from app.modules.ordering.auto_prep import AutoPrepService
from app.worker.jobs import Job

# How often auto-prep checks for due slots; an order moves at most this late.
AUTO_PREP_CHECK_S = 30


def auto_start_preparation() -> None:
    with get_sessionmaker()() as session:
        AutoPrepService(session).start_due(clock.now())


ORDERING_JOBS = [Job("auto-prep", auto_start_preparation, AUTO_PREP_CHECK_S)]
