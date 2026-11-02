"""caf-api: the FastAPI application. Run with `uvicorn app.main:app`."""

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.errors import add_error_handlers

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
    app = FastAPI(title="Caf@IITK API", version="0.1.0", generate_unique_id_function=_operation_id)
    settings = get_settings()
    # NFR-27: only the client's origin may call the API from a browser.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_origin_regex=None if settings.is_production else LOCAL_ORIGIN_REGEX,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "X-Request-ID"],
        expose_headers=["Retry-After"],
    )
    add_error_handlers(app)
    app.add_exception_handler(RequestValidationError, _validation_failed)
    app.include_router(api_router)

    @app.get("/health", tags=["ops"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
