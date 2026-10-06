"""mockpay: the separate mock payment service (FR-41, ADR-05).

Run with `uvicorn app.mockpay.main:app --port 8001` as a single process; the
ledger and the configured outcome are held in memory.

`PUT /_control/outcome` sets how the next authorisations are answered. It is
not registered when CAF_ENV=production, where every authorisation is approved.
Void and refund always succeed; stop the container to test an outage.
"""

import asyncio
from typing import Annotated, Literal

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from app.core.config import Settings, get_settings
from app.mockpay.ledger import AuthStatus, Ledger, LedgerConflictError

Reference = Annotated[str, Field(min_length=1, max_length=100)]


class Outcome(BaseModel):
    """How authorisations are answered until the outcome is set again."""

    model_config = ConfigDict(extra="forbid")

    mode: Literal["approve", "decline", "timeout"] = "approve"
    # Wait before an approve or decline answer; "approve after a delay" in FR-41.
    delay_ms: int = Field(default=0, ge=0, le=60_000)


class AuthoriseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reference: Reference
    amount_paise: int = Field(gt=0)


class VoidRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reference: Reference


class RefundRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reference: Reference
    auth_reference: Reference
    amount_paise: int = Field(gt=0)


class AuthorisationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    reference: str
    status: AuthStatus
    provider_ref: str | None


class RefundOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    reference: str
    auth_reference: str
    amount_paise: int


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(title="Caf@IITK mockpay", version="0.1.0")
    ledger = Ledger()
    app.state.outcome = Outcome()

    @app.exception_handler(LedgerConflictError)
    def ledger_conflict(request: Request, exc: LedgerConflictError) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status.HTTP_409_CONFLICT)

    @app.get("/health", tags=["ops"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/authorise", tags=["payments"])
    async def authorise(body: AuthoriseRequest) -> AuthorisationOut:
        outcome: Outcome = app.state.outcome
        if outcome.mode == "timeout":
            # Hold the request past the caller's P-PAY_TIMEOUT; nothing is authorised.
            await asyncio.sleep(settings.mockpay_hang_s)
            raise HTTPException(status.HTTP_504_GATEWAY_TIMEOUT, "Authorisation timed out")
        await asyncio.sleep(outcome.delay_ms / 1000)
        authorisation = ledger.authorise(
            body.reference, body.amount_paise, approve=outcome.mode == "approve"
        )
        return AuthorisationOut.model_validate(authorisation)

    @app.post("/void", tags=["payments"])
    async def void(body: VoidRequest) -> AuthorisationOut:
        return AuthorisationOut.model_validate(ledger.void(body.reference))

    @app.post("/refund", tags=["payments"])
    async def refund(body: RefundRequest) -> RefundOut:
        return RefundOut.model_validate(
            ledger.refund(body.reference, body.auth_reference, body.amount_paise)
        )

    if not settings.is_production:

        @app.get("/_control/outcome", tags=["control"])
        async def get_outcome() -> Outcome:
            outcome: Outcome = app.state.outcome
            return outcome

        @app.put("/_control/outcome", tags=["control"])
        async def set_outcome(body: Outcome) -> Outcome:
            app.state.outcome = body
            return body

    return app


app = create_app()
