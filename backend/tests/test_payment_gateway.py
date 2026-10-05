"""PaymentGateway adapter against mockpay over real HTTP (ADR-05), and the NFR-6 guard."""

import socket
import threading
import time
from collections.abc import Iterator

import httpx
import pytest
import uvicorn
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.mockpay.main import create_app
from app.modules.payments.fake import FakePaymentGateway
from app.modules.payments.gateway import (
    AuthOutcome,
    GatewayCalledInTransactionError,
    PaymentGatewayError,
    TransactionGuardedGateway,
)
from app.modules.payments.mockpay_gateway import (
    MockpayGateway,
    get_mockpay_client,
    get_payment_gateway,
)

# Stands in for P-PAY_TIMEOUT; mockpay's timeout mode holds requests for longer.
PAY_TIMEOUT_S = 0.3
HANG_S = 1.0


@pytest.fixture(scope="module")
def mockpay_url() -> Iterator[str]:
    """mockpay served by uvicorn on a free local port, so timeouts are real."""
    app = create_app(Settings(env="test", mockpay_hang_s=HANG_S))
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    server = uvicorn.Server(uvicorn.Config(app, log_level="warning", timeout_graceful_shutdown=2))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
    thread.start()
    while not server.started:
        time.sleep(0.01)
    yield f"http://127.0.0.1:{listener.getsockname()[1]}"
    server.should_exit = True
    thread.join(timeout=5)


@pytest.fixture
def control(mockpay_url: str) -> Iterator[httpx.Client]:
    with httpx.Client(base_url=mockpay_url) as client:
        yield client
        client.put("/_control/outcome", json={"mode": "approve"})


@pytest.fixture
def gateway(mockpay_url: str) -> Iterator[MockpayGateway]:
    with httpx.Client(base_url=mockpay_url, timeout=PAY_TIMEOUT_S) as client:
        yield MockpayGateway(client)


@pytest.fixture
def unreachable_gateway() -> Iterator[MockpayGateway]:
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    port = listener.getsockname()[1]
    listener.close()
    with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=PAY_TIMEOUT_S) as client:
        yield MockpayGateway(client)


def test_authorise_approved(gateway: MockpayGateway) -> None:
    result = gateway.authorise("approved-1", 8000)

    assert result.outcome is AuthOutcome.APPROVED
    assert result.provider_ref is not None


def test_authorise_declined(gateway: MockpayGateway, control: httpx.Client) -> None:
    control.put("/_control/outcome", json={"mode": "decline"})

    result = gateway.authorise("declined-1", 8000)

    assert result.outcome is AuthOutcome.DECLINED
    assert result.provider_ref is None


def test_authorise_gives_up_after_the_payment_timeout(
    gateway: MockpayGateway, control: httpx.Client
) -> None:
    control.put("/_control/outcome", json={"mode": "timeout"})

    started = time.monotonic()
    result = gateway.authorise("timeout-1", 8000)

    assert result.outcome is AuthOutcome.TIMEOUT
    assert PAY_TIMEOUT_S <= time.monotonic() - started < HANG_S


def test_void_after_a_timeout_stops_a_late_approval(
    gateway: MockpayGateway, control: httpx.Client
) -> None:
    control.put("/_control/outcome", json={"mode": "approve", "delay_ms": 600})
    assert gateway.authorise("late-1", 8000).outcome is AuthOutcome.TIMEOUT

    gateway.void("late-1")

    # Let the delayed authorisation finish, then ask again without a delay.
    time.sleep(0.7)
    control.put("/_control/outcome", json={"mode": "approve"})
    assert gateway.authorise("late-1", 8000).outcome is AuthOutcome.DECLINED
    with pytest.raises(PaymentGatewayError):
        gateway.refund("late-refund-1", "late-1", 8000)


def test_authorise_rejected_by_mockpay_is_not_treated_as_approved(gateway: MockpayGateway) -> None:
    gateway.authorise("reused-1", 8000)

    assert gateway.authorise("reused-1", 9000).outcome is AuthOutcome.TIMEOUT


def test_void_and_refund_are_acknowledged(gateway: MockpayGateway) -> None:
    gateway.authorise("settle-1", 8000)
    gateway.refund("settle-refund-1", "settle-1", 8000)
    gateway.refund("settle-refund-1", "settle-1", 8000)

    gateway.authorise("settle-2", 8000)
    gateway.void("settle-2")
    gateway.void("settle-2")


def test_refund_refused_by_mockpay_raises(gateway: MockpayGateway) -> None:
    with pytest.raises(PaymentGatewayError, match="409"):
        gateway.refund("orphan-refund-1", "never-authorised", 8000)


def test_unreachable_mockpay(unreachable_gateway: MockpayGateway) -> None:
    assert unreachable_gateway.authorise("down-1", 8000).outcome is AuthOutcome.TIMEOUT
    with pytest.raises(PaymentGatewayError):
        unreachable_gateway.void("down-1")
    with pytest.raises(PaymentGatewayError):
        unreachable_gateway.refund("down-refund-1", "down-1", 8000)


def test_gateway_refuses_to_run_inside_an_open_transaction(engine: Engine) -> None:
    fake = FakePaymentGateway()
    with Session(engine) as session:
        guarded = TransactionGuardedGateway(fake, session)
        session.execute(text("SELECT 1"))

        with pytest.raises(GatewayCalledInTransactionError):
            guarded.authorise("guard-1", 8000)
        with pytest.raises(GatewayCalledInTransactionError):
            guarded.void("guard-1")
        with pytest.raises(GatewayCalledInTransactionError):
            guarded.refund("guard-refund-1", "guard-1", 8000)
        assert not (fake.authorised or fake.voided or fake.refunded)

        session.commit()
        assert guarded.authorise("guard-1", 8000).outcome is AuthOutcome.APPROVED
        guarded.void("guard-1")
        guarded.refund("guard-refund-1", "guard-1", 8000)
        assert fake.authorised == [("guard-1", 8000)]
        assert fake.voided == ["guard-1"]
        assert fake.refunded == [("guard-refund-1", "guard-1", 8000)]


def test_fake_gateway_follows_its_script() -> None:
    fake = FakePaymentGateway(outcome=AuthOutcome.DECLINED, unavailable=True)

    assert fake.authorise("fake-1", 8000).provider_ref is None
    with pytest.raises(PaymentGatewayError):
        fake.void("fake-1")
    with pytest.raises(PaymentGatewayError):
        fake.refund("fake-refund-1", "fake-1", 8000)
    assert not (fake.voided or fake.refunded)


def test_request_gateway_is_guarded_and_configured_from_settings(
    engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CAF_MOCKPAY_URL", "http://mockpay.test:8001")
    monkeypatch.setenv("CAF_PAY_TIMEOUT_S", "7")
    for cached in (get_settings, get_mockpay_client):
        cached.cache_clear()
    try:
        client = get_mockpay_client()
        assert client.base_url == "http://mockpay.test:8001"
        assert client.timeout == httpx.Timeout(7)

        with Session(engine) as session:
            gateway = get_payment_gateway(session)
            session.execute(text("SELECT 1"))
            with pytest.raises(GatewayCalledInTransactionError):
                gateway.authorise("request-1", 8000)
    finally:
        get_mockpay_client().close()
        for cached in (get_settings, get_mockpay_client):
            cached.cache_clear()
