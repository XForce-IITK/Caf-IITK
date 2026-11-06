"""Exception handlers shared by every endpoint."""

import logging

from fastapi import FastAPI, Request, status
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import JSONResponse, Response
from sqlalchemy.exc import DBAPIError, InterfaceError, OperationalError
from sqlalchemy.exc import TimeoutError as PoolTimeoutError
from starlette.exceptions import HTTPException

from app.core import context

log = logging.getLogger("caf.api")

# NFR-16: how long the client should wait before trying again.
DATABASE_RETRY_AFTER_S = 5
# admin_shutdown, crash_shutdown, cannot_connect_now (still starting up)
_SHUTDOWN_SQLSTATES = frozenset({"57P01", "57P02", "57P03"})


def _connection_lost(exc: DBAPIError) -> bool:
    """Whether the database itself is unreachable, not merely refusing one statement.

    psycopg raises OperationalError for both a dead connection and, for example, a
    lock timeout. Only a connection problem means the whole database is down: no
    SQLSTATE (the client could not connect), class 08, or the server shutting down.
    """
    if exc.connection_invalidated or isinstance(exc, InterfaceError):
        return True
    sqlstate = getattr(exc.orig, "sqlstate", None)
    return sqlstate is None or sqlstate.startswith("08") or sqlstate in _SHUTDOWN_SQLSTATES


async def _database_unavailable(request: Request, exc: Exception) -> JSONResponse:
    """NFR-16: 503 with Retry-After, instead of a 500 or a hang, while the database is down.

    The request's transaction never committed, so nothing it did was written.
    """
    if isinstance(exc, DBAPIError) and not _connection_lost(exc):
        raise exc
    cause = (
        "connection pool exhausted" if isinstance(exc, PoolTimeoutError) else "database unavailable"
    )
    log.warning("%s: %s %s: %s", cause, request.method, request.url.path, exc)
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content=context.server_error_body(
            "The service is temporarily unavailable. Please try again shortly."
        ),
        headers={"Retry-After": str(DATABASE_RETRY_AFTER_S)},
    )


async def _http_error(request: Request, exc: Exception) -> Response:
    """A deliberate 5xx (`503 Busy, try again`) also carries the correlation ID (NFR-23).

    Only a plain-text detail is kept; anything structured is replaced by the
    generic message, since a 5xx must not describe the system's internals.
    """
    assert isinstance(exc, HTTPException)
    if exc.status_code < 500:
        return await http_exception_handler(request, exc)
    body = (
        context.server_error_body(exc.detail)
        if isinstance(exc.detail, str)
        else context.server_error_body()
    )
    return JSONResponse(body, status_code=exc.status_code, headers=exc.headers)


def add_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(HTTPException, _http_error)
    for error in (OperationalError, InterfaceError, PoolTimeoutError):
        app.add_exception_handler(error, _database_unavailable)
