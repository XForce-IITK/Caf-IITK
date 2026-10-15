"""The LLM client: a provider port plus the guards every call goes through (SADD 2.3).

`GuardedLLMClient.complete` checks, in order:

1. no database transaction is open on the caller's session (NFR-6);
2. the response cache: an identical request (same messages, tools and model, so
   the same tool data) on the same IST day is answered without a provider call;
3. the circuit breaker: after repeated failures the provider is not called until
   a cool-down passes;
4. the daily budget P-AGENT_DAILY_CAP, counted in `rate_limits` so it holds across
   processes (NFR-13, NFR-42).

Any failure surfaces as `LLMUnavailableError`; the agent then falls back to the
heuristic planner (FR-59). Tool-call arguments are returned as the raw string the
model produced, so malformed output reaches the validator (FR-58) instead of
failing here. The API key is never logged or returned.
"""

import hashlib
import json
import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import asdict, dataclass, replace
from datetime import date, datetime
from datetime import time as dtime
from typing import Literal, Protocol

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core import clock

Role = Literal["system", "user", "assistant", "tool"]

DAILY_BUDGET_SUBJECT = "llm:daily"


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    # JSON Schema of the tool's arguments.
    parameters: dict[str, object]


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: str


@dataclass(frozen=True)
class Message:
    role: Role
    content: str | None = None
    tool_calls: tuple[ToolCall, ...] = ()
    # For role "tool": the call this message answers.
    tool_call_id: str | None = None


@dataclass(frozen=True)
class LLMRequest:
    messages: tuple[Message, ...]
    tools: tuple[ToolSpec, ...] = ()


@dataclass(frozen=True)
class LLMResponse:
    content: str | None
    tool_calls: tuple[ToolCall, ...]
    model: str
    prompt_tokens: int | None
    completion_tokens: int | None
    latency_ms: int
    cached: bool = False


class LLMProviderError(Exception):
    """The provider failed: timeout, network error, error status or unusable reply."""


class LLMUnavailableError(Exception):
    """The LLM cannot be used for this request; fall back to the heuristic (FR-59)."""


class LLMBudgetExceededError(LLMUnavailableError):
    """P-AGENT_DAILY_CAP requests have already been made today."""


class LLMCalledInTransactionError(RuntimeError):
    pass


class LLMProvider(Protocol):
    model: str

    def complete(self, request: LLMRequest) -> LLMResponse:
        """One request to the model; raises LLMProviderError on any failure."""
        ...


def request_key(model: str, request: LLMRequest) -> str:
    canonical = json.dumps(
        {"model": model, "request": asdict(request)}, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


class ResponseCache:
    """Responses by request, kept for the IST day they were made on (FR-64)."""

    def __init__(self, max_entries: int = 256) -> None:
        self._entries: OrderedDict[tuple[date, str], LLMResponse] = OrderedDict()
        self._max_entries = max_entries
        self._lock = threading.Lock()

    def get(self, day: date, key: str) -> LLMResponse | None:
        with self._lock:
            response = self._entries.get((day, key))
            if response is not None:
                self._entries.move_to_end((day, key))
            return response

    def put(self, day: date, key: str, response: LLMResponse) -> None:
        with self._lock:
            for old in [k for k in self._entries if k[0] != day]:
                del self._entries[old]
            self._entries[(day, key)] = response
            self._entries.move_to_end((day, key))
            while len(self._entries) > self._max_entries:
                self._entries.popitem(last=False)


class CircuitBreaker:
    """Opens after `threshold` consecutive failures; allows one trial after `cooldown_s`.

    In-process state is fine here: it only protects availability and cost, and the
    agent runs in the single-leader worker (ADR-07).
    """

    def __init__(
        self,
        threshold: int = 3,
        cooldown_s: float = 60.0,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._threshold = threshold
        self._cooldown_s = cooldown_s
        self._monotonic = monotonic
        self._failures = 0
        self._opened_at: float | None = None
        self._lock = threading.Lock()

    def allow(self) -> bool:
        with self._lock:
            if self._opened_at is None:
                return True
            return self._monotonic() - self._opened_at >= self._cooldown_s

    def record_success(self) -> None:
        with self._lock:
            self._failures = 0
            self._opened_at = None

    def record_failure(self) -> None:
        with self._lock:
            self._failures += 1
            if self._failures >= self._threshold:
                # (Re)open: a failed trial after the cool-down starts a new cool-down.
                self._opened_at = self._monotonic()


def consume_daily_budget(session: Session, daily_cap: int, now: datetime) -> bool:
    """Count one LLM request against today's cap in its own short transaction."""
    day_start = datetime.combine(now.date(), dtime.min, tzinfo=clock.IST)
    with session.begin():
        count = session.execute(
            text(
                "INSERT INTO rate_limits (subject, window_start, count) "
                "VALUES (:subject, :window, 1) "
                "ON CONFLICT (subject, window_start) "
                "DO UPDATE SET count = rate_limits.count + 1 WHERE rate_limits.count < :cap "
                "RETURNING count"
            ),
            {"subject": DAILY_BUDGET_SUBJECT, "window": day_start, "cap": daily_cap},
        ).scalar_one_or_none()
    return count is not None and count <= daily_cap


class GuardedLLMClient:
    def __init__(
        self,
        provider: LLMProvider | None,
        session: Session,
        *,
        daily_cap: int,
        breaker: CircuitBreaker,
        cache: ResponseCache,
        now: Callable[[], datetime] = clock.now,
    ) -> None:
        self._provider = provider
        self._session = session
        self._daily_cap = daily_cap
        self._breaker = breaker
        self._cache = cache
        self._now = now

    def complete(self, request: LLMRequest) -> LLMResponse:
        if self._session.in_transaction():
            raise LLMCalledInTransactionError("LLM called while a database transaction is open")
        if self._provider is None:
            raise LLMUnavailableError("no LLM API key is configured")
        now = self._now()
        key = request_key(self._provider.model, request)
        cached = self._cache.get(now.date(), key)
        if cached is not None:
            return replace(cached, cached=True, latency_ms=0)
        if not self._breaker.allow():
            raise LLMUnavailableError("LLM circuit breaker is open")
        if not consume_daily_budget(self._session, self._daily_cap, now):
            raise LLMBudgetExceededError(f"daily LLM cap of {self._daily_cap} reached")
        try:
            response = self._provider.complete(request)
        except LLMProviderError as exc:
            self._breaker.record_failure()
            raise LLMUnavailableError(str(exc)) from exc
        self._breaker.record_success()
        self._cache.put(now.date(), key, response)
        return response
