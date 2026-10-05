"""mockpay: the separate mock payment service (FR-41).

Run with `uvicorn app.mockpay.main:app --port 8001`. Authorise, void, refund
and the non-production outcome control are added under CAFIITK-148 / FR-41.
"""

from fastapi import FastAPI


def create_app() -> FastAPI:
    app = FastAPI(title="Caf@IITK mockpay", version="0.1.0")

    @app.get("/health", tags=["ops"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
