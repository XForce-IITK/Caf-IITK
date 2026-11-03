"""Structured JSON logs (NFR-28) with secrets removed (NFR-30).

One JSON object per line on stderr: timestamp, level, logger, message, the
correlation ID and internal user ID from the request context, any `extra` fields
(the access log adds method, route, status and latency_ms) and the traceback.

`RedactingFilter` runs on the handler, so it sees every record from every logger:
it rewrites the message, the extra fields and the traceback, removing passwords,
tokens, API keys, credentials in URLs and card numbers. Code should still never
log a request body; the filter is the safety net, not the policy.
"""

import json
import logging
import re
import sys
from datetime import UTC, datetime
from typing import Any

from app.core import context

REDACTED = "[REDACTED]"

# Field names whose values are secret: password, refresh_token, api_key, X-API-Key,
# Authorization, card_number... but not prompt_tokens, which is a count.
_SECRET_KEY = re.compile(
    r"(?:^|[_-])(?:password|passwd|secret|token|api[_-]?key|authorization|card[_-]?number|cvv)$",
    re.IGNORECASE,
)
_SECRET_KEY_TEXT = (
    r"[\w-]*?(?:password|passwd|secret|token|api[_-]?key|authorization|card[_-]?number|cvv)"
)
_TEXT_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # Authorization: Bearer <jwt>
    (re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]+", re.IGNORECASE), f"Bearer {REDACTED}"),
    # A JWT anywhere: header.payload.signature, the header always starting {"
    (re.compile(r"\beyJ[\w-]*\.[\w-]+\.[\w-]*"), REDACTED),
    # Provider API keys (sk-..., sk-proj-...).
    (re.compile(r"\bsk-[A-Za-z0-9_-]{8,}"), REDACTED),
    # The password in postgresql+psycopg://user:password@host/db
    (re.compile(r"(://[^:/@\s]+:)[^@\s]+@"), rf"\1{REDACTED}@"),
    # password=..., "refresh_token": "...", api_key: ...
    (
        re.compile(
            rf"""(\b{_SECRET_KEY_TEXT}["']?\s*[:=]\s*)("[^"]*"|'[^']*'|[^\s,;&)}}\]]+)""",
            re.IGNORECASE,
        ),
        rf"\1{REDACTED}",
    ),
]
_CARD = re.compile(r"\b\d(?:[ -]?\d){12,18}\b")


def _luhn(digits: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(digits)):
        n = int(ch)
        if i % 2:
            n = n * 2 - 9 if n > 4 else n * 2
        total += n
    return total % 10 == 0


def _card(match: re.Match[str]) -> str:
    digits = re.sub(r"\D", "", match.group())
    return REDACTED if _luhn(digits) else match.group()


def redact(text: str) -> str:
    for pattern, replacement in _TEXT_PATTERNS:
        text = pattern.sub(replacement, text)
    return _CARD.sub(_card, text)


def redact_value(key: str, value: Any) -> Any:
    if _SECRET_KEY.search(key):
        return REDACTED
    if isinstance(value, str):
        return redact(value)
    if isinstance(value, dict):
        return {k: redact_value(str(k), v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [redact_value(key, v) for v in value]
    return value


# Attributes every LogRecord has; anything else came in through `extra`.
_STANDARD = frozenset(logging.makeLogRecord({}).__dict__) | {"message", "asctime"}
_CONTEXT = ("correlation_id", "user_id")


def _extras(record: logging.LogRecord) -> dict[str, Any]:
    return {k: v for k, v in record.__dict__.items() if k not in _STANDARD and k not in _CONTEXT}


class ContextFilter(logging.Filter):
    """Stamps each record with the correlation ID and user ID current when it was logged."""

    def filter(self, record: logging.LogRecord) -> bool:
        current = context.current()
        record.correlation_id = current.correlation_id if current else None
        record.user_id = current.user_id if current else None
        return True


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact(record.getMessage())
        record.args = None
        for key, value in _extras(record).items():
            setattr(record, key, redact_value(key, value))
        if record.exc_info and not record.exc_text:
            record.exc_text = logging.Formatter().formatException(record.exc_info)
        if record.exc_text:
            record.exc_text = redact(record.exc_text)
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "correlation_id": getattr(record, "correlation_id", None),
            "user_id": getattr(record, "user_id", None),
            **_extras(record),
        }
        if record.exc_info and not record.exc_text:
            record.exc_text = self.formatException(record.exc_info)
        if record.exc_text:
            entry["exception"] = record.exc_text
        return json.dumps(entry, default=str)


class CafLogHandler(logging.StreamHandler):  # type: ignore[type-arg]
    def __init__(self) -> None:
        super().__init__(sys.stderr)
        self.addFilter(ContextFilter())
        self.addFilter(RedactingFilter())
        self.setFormatter(JsonFormatter())


def configure_logging(level: int = logging.INFO) -> None:
    """Send every logger's records to stderr as JSON; safe to call more than once."""
    root = logging.getLogger()
    if not any(isinstance(handler, CafLogHandler) for handler in root.handlers):
        root.addHandler(CafLogHandler())
    root.setLevel(level)
