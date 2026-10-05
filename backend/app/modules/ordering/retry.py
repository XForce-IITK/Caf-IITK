"""Bounded retry of a transaction that lost a deadlock or serialisation race (NFR-4)."""

import random
import time
from collections.abc import Callable

from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

MAX_RETRIES = 3
_BASE_BACKOFF_S = 0.02
# serialization_failure, deadlock_detected
_TRANSIENT_SQLSTATES = frozenset({"40001", "40P01"})


class TransientFailureError(Exception):
    """Still failing after MAX_RETRIES retries: 503, nothing was written."""


def is_transient(exc: DBAPIError) -> bool:
    return getattr(exc.orig, "sqlstate", None) in _TRANSIENT_SQLSTATES


def run_in_transaction[T](
    session: Session, work: Callable[[], T], *, sleep: Callable[[float], None] = time.sleep
) -> T:
    """Run `work` in one transaction, retrying a transient failure with jittered back-off.

    `work` must be safe to repeat: every attempt starts from a rolled-back session.
    """
    for attempt in range(MAX_RETRIES + 1):
        try:
            with session.begin():
                return work()
        except DBAPIError as exc:
            if not is_transient(exc):
                raise
            if attempt == MAX_RETRIES:
                raise TransientFailureError from exc
            sleep(random.uniform(0, _BASE_BACKOFF_S * 2**attempt))
    raise AssertionError("unreachable")  # pragma: no cover
