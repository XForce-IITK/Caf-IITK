"""Rate limits with counters shared in PostgreSQL (NFR-21, NFR-13).

Failed logins are limited per account and per client IP, and order create,
modify and cancel per Student. Counters live in `rate_limits`, one row per
subject and minute, so a limit holds however many API workers run.

A login attempt takes its place in the window before the password is checked,
and gives it back if the login succeeds. Checking first and counting afterwards
would let a burst of parallel guesses all pass the check before any of them was
counted.
"""

import hashlib
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.core import clock
from app.modules.identity.repository import RateLimitRepository

WINDOW = timedelta(minutes=1)
# Old windows are deleted after this; the agent's daily LLM budget shares the table.
KEEP_WINDOWS_FOR = timedelta(days=2)


class RateLimitExceededError(Exception):
    def __init__(self, retry_after_s: int) -> None:
        super().__init__(f"rate limit exceeded; retry after {retry_after_s} s")
        self.retry_after_s = retry_after_s


def login_account_subject(email: str) -> str:
    # Hashed, so the table holds no email addresses, including ones that are not accounts.
    return "login-account:" + hashlib.sha256(email.encode()).hexdigest()


def login_ip_subject(ip: str) -> str:
    return f"login-ip:{ip}"


def order_subject(user_id: uuid.UUID) -> str:
    return f"order:{user_id}"


@dataclass(frozen=True)
class Reservation:
    subjects: tuple[str, ...]
    window_start: datetime


class RateLimiter:
    """Each method runs its own short transaction; call it with no transaction open."""

    def __init__(self, session: Session, now: Callable[[], datetime] | None = None) -> None:
        self.session = session
        self.counters = RateLimitRepository(session)
        self.now = now or clock.now

    def take(self, subjects: Sequence[str], cap: int) -> Reservation:
        """Count one against every subject, or none of them and raise RateLimitExceededError."""
        now = self.now()
        window_start = now.replace(second=0, microsecond=0)
        with self.session.begin():
            for subject in subjects:
                if not self.counters.take(subject, window_start, cap):
                    # Leaving the block rolls back the subjects already counted.
                    raise RateLimitExceededError(_seconds_until(window_start + WINDOW, now))
        return Reservation(tuple(subjects), window_start)

    def give_back(self, reservation: Reservation) -> None:
        with self.session.begin():
            for subject in reservation.subjects:
                self.counters.give_back(subject, reservation.window_start)

    def delete_old_windows(self) -> int:
        with self.session.begin():
            return self.counters.delete_before(self.now() - KEEP_WINDOWS_FOR)


def _seconds_until(moment: datetime, now: datetime) -> int:
    return max(1, int((moment - now).total_seconds() + 0.999))
