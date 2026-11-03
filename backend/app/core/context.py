"""Request context: the correlation ID and the caller's user ID (NFR-29).

Every request gets a correlation ID: the client's `X-Request-ID` if it is a safe
token, or a new one. It is returned in the response's `X-Request-ID`, added to
every log line, written to audit rows, stored on agent runs requested in that
request, and forwarded to mockpay. caf-worker gives each job run its own ID.

A 5xx body is a generic message and this ID, nothing else (NFR-23): the details
are in the log line with the same ID. An unhandled exception becomes such a 500
here, so its traceback, SQL or file paths never reach the client.

The context lives in a ContextVar holding a mutable object: sync endpoints run in
a threadpool with a copy of the context, so they cannot set a variable the
middleware would see, but they can fill in the user ID on the shared object.
"""

import logging
import re
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass

from starlette.datastructures import Headers, MutableHeaders
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.routing import route_template

HEADER = "X-Request-ID"
# Long enough for a UUID or a trace ID; nothing that could break a log line.
_ACCEPTED = re.compile(r"[A-Za-z0-9._:-]{1,128}")
# Docker and Prometheus call these every few seconds; they would drown the log.
_QUIET_ROUTES = frozenset({"/health", "/ready", "/metrics"})
SERVER_ERROR_MESSAGE = "Something went wrong. Please try again later."

access_log = logging.getLogger("caf.access")


@dataclass
class RequestContext:
    correlation_id: str
    user_id: str | None = None


_current: ContextVar[RequestContext | None] = ContextVar("caf_request_context", default=None)


def new_correlation_id() -> str:
    return uuid.uuid4().hex


def current() -> RequestContext | None:
    return _current.get()


def correlation_id() -> str | None:
    context = _current.get()
    return context.correlation_id if context else None


def set_user(user_id: uuid.UUID) -> None:
    """Called once the caller is authenticated, so later log lines name them."""
    context = _current.get()
    if context is not None:
        context.user_id = str(user_id)


def server_error_body(message: str = SERVER_ERROR_MESSAGE) -> dict[str, str | None]:
    """The whole body of a 5xx response (NFR-23)."""
    return {"detail": message, "correlation_id": correlation_id()}


@contextmanager
def correlation(correlation_id: str | None = None) -> Iterator[RequestContext]:
    """Run the block under `correlation_id`, or a new one; for work outside a request."""
    context = RequestContext(correlation_id or new_correlation_id())
    token = _current.set(context)
    try:
        yield context
    finally:
        _current.reset(token)


class RequestContextMiddleware:
    """Sets the request context, returns X-Request-ID, and writes one access log line."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        offered = Headers(scope=scope).get(HEADER, "")
        started = time.perf_counter()
        status = 500
        response_started = False

        async def send_wrapper(message: Message) -> None:
            nonlocal status, response_started
            if message["type"] == "http.response.start":
                status = message["status"]
                response_started = True
                MutableHeaders(scope=message)[HEADER] = context.correlation_id
            await send(message)

        with correlation(offered if _ACCEPTED.fullmatch(offered) else None) as context:
            try:
                await self.app(scope, receive, send_wrapper)
            except Exception:
                access_log.exception("unhandled error")
                if response_started:
                    raise
                # Not re-raised: the server would print the traceback again, unredacted.
                response = JSONResponse(server_error_body(), status_code=500)
                await response(scope, receive, send_wrapper)
            finally:
                route = route_template(scope)
                access_log.log(
                    logging.DEBUG if route in _QUIET_ROUTES else logging.INFO,
                    "%s %s %s",
                    scope["method"],
                    route,
                    status,
                    extra={
                        "method": scope["method"],
                        "route": route,
                        "status": status,
                        "latency_ms": round((time.perf_counter() - started) * 1000, 1),
                    },
                )
