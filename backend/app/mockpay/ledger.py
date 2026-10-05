"""In-memory record of what mockpay has authorised, voided and refunded.

Every operation is keyed by a caller-chosen reference, so a retried request
returns the first result instead of acting twice (FR-39). State lives in the
process: mockpay runs as a single process and forgets everything on restart.
"""

import uuid
from dataclasses import dataclass
from enum import StrEnum
from threading import Lock


class AuthStatus(StrEnum):
    APPROVED = "APPROVED"
    DECLINED = "DECLINED"
    VOIDED = "VOIDED"


@dataclass
class Authorisation:
    reference: str
    amount_paise: int
    status: AuthStatus
    provider_ref: str | None = None
    refunded_paise: int = 0


@dataclass(frozen=True)
class Refund:
    reference: str
    auth_reference: str
    amount_paise: int


class LedgerConflictError(Exception):
    pass


class Ledger:
    def __init__(self) -> None:
        self._lock = Lock()
        self._authorisations: dict[str, Authorisation] = {}
        self._refunds: dict[str, Refund] = {}

    def authorise(self, reference: str, amount_paise: int, *, approve: bool) -> Authorisation:
        with self._lock:
            existing = self._authorisations.get(reference)
            if existing is not None:
                # A void that arrived first leaves a VOIDED record with no amount.
                if existing.status is not AuthStatus.VOIDED and existing.amount_paise != (
                    amount_paise
                ):
                    raise LedgerConflictError("reference already used with a different amount")
                return existing
            authorisation = Authorisation(
                reference=reference,
                amount_paise=amount_paise,
                status=AuthStatus.APPROVED if approve else AuthStatus.DECLINED,
                provider_ref=f"mp_{uuid.uuid4().hex}" if approve else None,
            )
            self._authorisations[reference] = authorisation
            return authorisation

    def void(self, reference: str) -> Authorisation:
        """Cancel an authorisation, or block one that has not arrived yet.

        Voiding an unknown reference records it as VOIDED, so an authorise that
        is still in flight (a late approval, FR-34) cannot succeed afterwards.
        """
        with self._lock:
            authorisation = self._authorisations.get(reference)
            if authorisation is None:
                authorisation = Authorisation(reference, 0, AuthStatus.VOIDED)
                self._authorisations[reference] = authorisation
            elif authorisation.refunded_paise > 0:
                raise LedgerConflictError("authorisation has refunds and cannot be voided")
            elif authorisation.status is AuthStatus.APPROVED:
                authorisation.status = AuthStatus.VOIDED
            return authorisation

    def refund(self, reference: str, auth_reference: str, amount_paise: int) -> Refund:
        with self._lock:
            refund = Refund(reference, auth_reference, amount_paise)
            existing = self._refunds.get(reference)
            if existing is not None:
                if existing != refund:
                    raise LedgerConflictError("reference already used for a different refund")
                return existing
            authorisation = self._authorisations.get(auth_reference)
            if authorisation is None or authorisation.status is not AuthStatus.APPROVED:
                raise LedgerConflictError("no approved authorisation with this reference")
            if authorisation.refunded_paise + amount_paise > authorisation.amount_paise:
                raise LedgerConflictError("refunds would exceed the authorised amount")
            authorisation.refunded_paise += amount_paise
            self._refunds[reference] = refund
            return refund
