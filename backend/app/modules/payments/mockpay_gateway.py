"""HTTP adapter from `PaymentGateway` to the mockpay service (ADR-05)."""

import logging
from functools import lru_cache
from typing import Annotated, Any

import httpx
from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_session
from app.modules.payments.gateway import (
    AuthOutcome,
    AuthResult,
    PaymentGateway,
    PaymentGatewayError,
    TransactionGuardedGateway,
)

logger = logging.getLogger(__name__)


class MockpayGateway:
    """`client` carries the mockpay base URL and the P-PAY_TIMEOUT timeout."""

    def __init__(self, client: httpx.Client) -> None:
        self._client = client

    def authorise(self, reference: str, amount_paise: int) -> AuthResult:
        try:
            response = self._client.post(
                "/authorise", json={"reference": reference, "amount_paise": amount_paise}
            )
        except httpx.HTTPError as exc:
            logger.warning("mockpay authorise %s got no answer: %r", reference, exc)
            return AuthResult(AuthOutcome.TIMEOUT)
        if response.status_code != httpx.codes.OK:
            logger.warning("mockpay authorise %s answered %s", reference, response.status_code)
            return AuthResult(AuthOutcome.TIMEOUT)
        body = response.json()
        if body["status"] != "APPROVED":
            return AuthResult(AuthOutcome.DECLINED)
        return AuthResult(AuthOutcome.APPROVED, provider_ref=body["provider_ref"])

    def void(self, reference: str) -> None:
        self._settle("/void", {"reference": reference})

    def refund(self, reference: str, auth_reference: str, amount_paise: int) -> None:
        self._settle(
            "/refund",
            {
                "reference": reference,
                "auth_reference": auth_reference,
                "amount_paise": amount_paise,
            },
        )

    def _settle(self, path: str, payload: dict[str, Any]) -> None:
        try:
            response = self._client.post(path, json=payload)
        except httpx.HTTPError as exc:
            raise PaymentGatewayError(f"mockpay {path} got no answer: {exc!r}") from exc
        if response.status_code != httpx.codes.OK:
            raise PaymentGatewayError(f"mockpay {path} answered {response.status_code}")


@lru_cache
def get_mockpay_client() -> httpx.Client:
    settings = get_settings()
    return httpx.Client(base_url=settings.mockpay_url, timeout=settings.pay_timeout_s)


def get_payment_gateway(session: Annotated[Session, Depends(get_session)]) -> PaymentGateway:
    """The gateway for a request; guarded by the same session the route receives."""
    return TransactionGuardedGateway(MockpayGateway(get_mockpay_client()), session)
