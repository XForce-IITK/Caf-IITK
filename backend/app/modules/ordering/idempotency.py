"""Idempotency keys for create, modify and cancel (FR-32, NFR-7, NFR-18).

How an endpoint uses it, inside the transaction that makes the change:

    with session.begin():
        replay = IdempotencyService(session).claim(student.id, key, payload)
        if replay is not None:
            return replay.response              # same key + same payload: original result
        order = ...                             # do the work exactly once
        IdempotencyService(session).complete(student.id, key, {"order_id": ...})

Why it is exactly-once: `claim` inserts the (student, key) row in the caller's
transaction. A concurrent duplicate's insert collides on the primary key and
waits until the first transaction ends: on commit it sees the stored result and
replays it; on rollback its own insert succeeds and it does the work instead.

Order placement commits before calling mockpay (NFR-6). If `complete` happens in
the later transaction, a duplicate arriving in between gets
RequestInProgressError (409), and the client's retry with the same key
(NFR-18) picks up the final result.
"""

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from fastapi import Header
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.enums import IdempotencyState
from app.models.ordering import IdempotencyKey

# Client-generated (UUIDs in practice): 1-100 URL-safe characters.
IdempotencyKeyHeader = Annotated[
    str,
    Header(alias="Idempotency-Key", min_length=1, max_length=100, pattern=r"^[A-Za-z0-9._:-]+$"),
]


class IdempotencyKeyReusedError(Exception):
    """The key was already used with a different payload (FR-32): 422."""


class RequestInProgressError(Exception):
    """The original request with this key has not finished yet: 409, retry later."""


@dataclass(frozen=True)
class Replay:
    response: dict[str, Any]


def request_hash(payload: Any) -> str:
    """Stable hash of the request payload; key order and whitespace do not matter."""
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()


class IdempotencyRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def insert_if_absent(self, user_id: uuid.UUID, key: str, request_hash: str) -> bool:
        inserted = self.session.execute(
            insert(IdempotencyKey)
            .values(
                user_id=user_id,
                key=key,
                request_hash=request_hash,
                state=IdempotencyState.IN_PROGRESS,
            )
            .on_conflict_do_nothing()
            .returning(IdempotencyKey.key)
        ).first()
        return inserted is not None

    def get(self, user_id: uuid.UUID, key: str) -> IdempotencyKey:
        return self.session.scalars(
            select(IdempotencyKey)
            .where(IdempotencyKey.user_id == user_id, IdempotencyKey.key == key)
            .execution_options(populate_existing=True)
        ).one()

    def reclaim_expired(
        self, user_id: uuid.UUID, key: str, request_hash: str, cutoff: datetime
    ) -> bool:
        """Take over a key older than P-IDEM_TTL; atomic, so only one request wins."""
        reclaimed = self.session.execute(
            update(IdempotencyKey)
            .where(
                IdempotencyKey.user_id == user_id,
                IdempotencyKey.key == key,
                IdempotencyKey.created_at < cutoff,
            )
            .values(
                request_hash=request_hash,
                state=IdempotencyState.IN_PROGRESS,
                response=None,
                created_at=datetime.now(UTC),
            )
            .returning(IdempotencyKey.key)
        ).first()
        return reclaimed is not None

    def complete(self, user_id: uuid.UUID, key: str, response: dict[str, Any]) -> None:
        self.session.execute(
            update(IdempotencyKey)
            .where(IdempotencyKey.user_id == user_id, IdempotencyKey.key == key)
            .values(state=IdempotencyState.COMPLETED, response=response)
        )


class IdempotencyService:
    def __init__(self, session: Session) -> None:
        self.repo = IdempotencyRepository(session)

    def claim(self, user_id: uuid.UUID, key: str, payload: Any) -> Replay | None:
        """Claim `key` for this request. Call inside the caller's transaction.

        Returns None when the caller should do the work (then call `complete`), or a
        Replay of the stored result for a repeat. Raises IdempotencyKeyReusedError for
        the same key with a different payload, RequestInProgressError while the
        original request is unfinished. Keys are scoped to the user.
        """
        digest = request_hash(payload)
        if self.repo.insert_if_absent(user_id, key, digest):
            return None
        cutoff = datetime.now(UTC) - timedelta(hours=get_settings().idem_ttl_h)
        if self.repo.reclaim_expired(user_id, key, digest, cutoff):
            return None
        existing = self.repo.get(user_id, key)
        if existing.request_hash != digest:
            raise IdempotencyKeyReusedError
        if existing.state is IdempotencyState.IN_PROGRESS or existing.response is None:
            raise RequestInProgressError
        return Replay(existing.response)

    def complete(self, user_id: uuid.UUID, key: str, response: dict[str, Any]) -> None:
        """Store the result a repeat of this request should get."""
        self.repo.complete(user_id, key, response)
