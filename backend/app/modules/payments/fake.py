"""In-memory `PaymentGateway` for tests that do not need real HTTP (SADD P9)."""

from dataclasses import dataclass, field

from app.modules.payments.gateway import AuthOutcome, AuthResult, PaymentGatewayError


@dataclass
class FakePaymentGateway:
    """Answers every authorisation with `outcome` and records what it was asked."""

    outcome: AuthOutcome = AuthOutcome.APPROVED
    # When set, void and refund fail as they do while mockpay is down.
    unavailable: bool = False
    authorised: list[tuple[str, int]] = field(default_factory=list)
    voided: list[str] = field(default_factory=list)
    refunded: list[tuple[str, str, int]] = field(default_factory=list)

    def authorise(self, reference: str, amount_paise: int) -> AuthResult:
        self.authorised.append((reference, amount_paise))
        if self.outcome is AuthOutcome.APPROVED:
            return AuthResult(self.outcome, provider_ref=f"fake_{reference}")
        return AuthResult(self.outcome)

    def void(self, reference: str) -> None:
        self._require_available()
        self.voided.append(reference)

    def refund(self, reference: str, auth_reference: str, amount_paise: int) -> None:
        self._require_available()
        self.refunded.append((reference, auth_reference, amount_paise))

    def _require_available(self) -> None:
        if self.unavailable:
            raise PaymentGatewayError("payment gateway unavailable")
