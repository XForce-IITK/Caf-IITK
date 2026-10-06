"""caf-api: the FastAPI application. Run with `uvicorn app.main:app`."""

from fastapi import FastAPI
from fastapi.routing import APIRoute

from app.api.v1.router import api_router


def _operation_id(route: APIRoute) -> str:
    """The endpoint function's name, so the generated Dart client reads `placeOrder`."""
    return route.name


def create_app() -> FastAPI:
    app = FastAPI(title="Caf@IITK API", version="0.1.0", generate_unique_id_function=_operation_id)
    app.include_router(api_router)

    @app.get("/health", tags=["ops"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
