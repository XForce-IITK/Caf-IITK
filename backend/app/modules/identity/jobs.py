"""The identity module's caf-worker job: delete old rate-limit windows (NFR-21)."""

from app.db.session import get_sessionmaker
from app.modules.identity.rate_limit import RateLimiter
from app.worker.jobs import Job

CLEANUP_INTERVAL_S = 3600


def delete_old_rate_limit_windows() -> None:
    with get_sessionmaker()() as session:
        RateLimiter(session).delete_old_windows()


IDENTITY_JOBS = [Job("rate-limit-cleanup", delete_old_rate_limit_windows, CLEANUP_INTERVAL_S)]
