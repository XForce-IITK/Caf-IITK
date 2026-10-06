"""caf-api: the FastAPI application. Run with `uvicorn app.main:app`."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.routing import APIRoute

from app.api.v1.router import api_router
from app.core.config import get_settings

LOCAL_ORIGIN_REGEX = r"^http://(localhost|127\.0\.0\.1)(:\d+)?$"


def _operation_id(route: APIRoute) -> str:
    """The endpoint function's name, so the generated Dart client reads `placeOrder`."""
    return route.name


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
    app.include_router(api_router)

    @app.get("/health", tags=["ops"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
