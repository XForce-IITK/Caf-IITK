"""caf-api: the FastAPI application. Run with `uvicorn app.main:app`."""

from fastapi import Depends, FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute

from app.api.ops import router as ops_router
from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.context import HEADER as REQUEST_ID_HEADER
from app.core.context import RequestContextMiddleware
from app.core.errors import add_error_handlers
from app.core.logs import configure_logging
from app.core.metrics import MetricsMiddleware
from app.core.validation import reject_unknown_query_params
from app.modules.identity.cookie import TRANSPORT_HEADER

LOCAL_ORIGIN_REGEX = r"^http://(localhost|127\.0\.0\.1)(:\d+)?$"


def _operation_id(route: APIRoute) -> str:
    """The endpoint function's name, so the generated Dart client reads `placeOrder`."""
    return route.name


async def _validation_failed(request: Request, exc: Exception) -> JSONResponse:
    """422 with field-level messages (NFR-22) that never echo the submitted value.

    FastAPI's default handler returns each rejected value as `input`, which sent a
    too-short password straight back to the client (NFR-20).
    """
    assert isinstance(exc, RequestValidationError)
    errors = [{k: v for k, v in error.items() if k != "input"} for error in exc.errors()]
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content=jsonable_encoder({"detail": errors}),
    )


def create_app() -> FastAPI:
    configure_logging()
    app = FastAPI(
        title="Caf@IITK API",
        version="0.1.0",
        generate_unique_id_function=_operation_id,
        # NFR-22: an unknown query parameter is a 422, like an unknown body field.
        dependencies=[Depends(reject_unknown_query_params)],
    )
    settings = get_settings()
    # NFR-27: only the client's origin may call the API from a browser.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_origin_regex=None if settings.is_production else LOCAL_ORIGIN_REGEX,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=[
            "Authorization",
            "Content-Type",
            "Idempotency-Key",
            REQUEST_ID_HEADER,
            TRANSPORT_HEADER,
        ],
        # CAFIITK-207: the refresh-token cookie must reach /auth from the client's origin.
        allow_credentials=True,
        expose_headers=["Retry-After", REQUEST_ID_HEADER],
    )
    # Outermost, so the time recorded includes every other middleware (NFR-31).
    app.add_middleware(MetricsMiddleware)
    # NFR-29: outermost of all, so every log line of the request carries its ID.
    app.add_middleware(RequestContextMiddleware)
    add_error_handlers(app)
    app.add_exception_handler(RequestValidationError, _validation_failed)
    app.include_router(api_router)
    app.include_router(ops_router)
    return app


app = create_app()
