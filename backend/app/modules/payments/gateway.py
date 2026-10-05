"""The payment gateway port (SADD P9) and the guard that enforces NFR-6.

Services depend on `PaymentGateway`, never on mockpay directly. References are
chosen by the caller (the `payments.id` of the row being settled) and make
every call safe to repeat.
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from sqlalchemy.orm import Session


class AuthOutcome(StrEnum):
    APPROVED = "APPROVED"
    DECLINED = "DECLINED"
    # No usable answer within P-PAY_TIMEOUT. The payment may still have been
    # authorised, so the caller must queue a void (SADD 6.2).
    TIMEOUT = "TIMEOUT"


@dataclass(frozen=True)
class AuthResult:
    outcome: AuthOutcome
    provider_ref: str | None = None


class PaymentGatewayError(Exception):
    """A void or refund was not acknowledged; the outbox retries it (FR-39)."""


class GatewayCalledInTransactionError(RuntimeError):
    pass


class PaymentGateway(Protocol):
    def authorise(self, reference: str, amount_paise: int) -> AuthResult: ...

    def void(self, reference: str) -> None:
        """Cancel the authorisation made under `reference`, whether or not it has landed."""
        ...

    def refund(self, reference: str, auth_reference: str, amount_paise: int) -> None: ...


class TransactionGuardedGateway:
    """Refuses every call while `session` has a transaction open (NFR-6).

    A network call inside a transaction would hold row locks for up to
    P-PAY_TIMEOUT. Commit or roll back first: reserve → authorise → confirm.
    """

    def __init__(self, inner: PaymentGateway, session: Session) -> None:
        self._inner = inner
        self._session = session

    def _require_no_transaction(self) -> None:
        if self._session.in_transaction():
            raise GatewayCalledInTransactionError(
                "payment gateway called while a database transaction is open"
            )

    def authorise(self, reference: str, amount_paise: int) -> AuthResult:
        self._require_no_transaction()
        return self._inner.authorise(reference, amount_paise)

    def void(self, reference: str) -> None:
        self._require_no_transaction()
        self._inner.void(reference)

    def refund(self, reference: str, auth_reference: str, amount_paise: int) -> None:
        self._require_no_transaction()
        self._inner.refund(reference, auth_reference, amount_paise)
