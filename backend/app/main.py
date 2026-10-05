"""caf-api: the FastAPI application. Run with `uvicorn app.main:app`."""

from fastapi import FastAPI

from app.api.v1.router import api_router


def create_app() -> FastAPI:
    app = FastAPI(title="Caf@IITK API", version="0.1.0")
    app.include_router(api_router)

    @app.get("/health", tags=["ops"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
