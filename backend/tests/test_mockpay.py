"""mockpay service (FR-41): authorise, void, refund and the outcome control."""

import time

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.mockpay.main import create_app

AUTH = {"reference": "pay-1", "amount_paise": 8000}


@pytest.fixture
def mockpay() -> TestClient:
    return TestClient(create_app(Settings(env="test", mockpay_hang_s=0.05)))


def _set_outcome(mockpay: TestClient, **outcome: object) -> None:
    assert mockpay.put("/_control/outcome", json=outcome).status_code == 200


def test_authorise_approves_by_default(mockpay: TestClient) -> None:
    response = mockpay.post("/authorise", json=AUTH)

    assert response.status_code == 200
    body = response.json()
    assert body["reference"] == "pay-1"
    assert body["status"] == "APPROVED"
    assert body["provider_ref"].startswith("mp_")


def test_repeated_authorise_returns_the_first_result(mockpay: TestClient) -> None:
    first = mockpay.post("/authorise", json=AUTH).json()
    _set_outcome(mockpay, mode="decline")

    assert mockpay.post("/authorise", json=AUTH).json() == first


def test_authorise_reference_reused_with_another_amount_gets_409(mockpay: TestClient) -> None:
    mockpay.post("/authorise", json=AUTH)

    response = mockpay.post("/authorise", json={**AUTH, "amount_paise": 9000})

    assert response.status_code == 409


def test_decline_outcome(mockpay: TestClient) -> None:
    _set_outcome(mockpay, mode="decline")

    body = mockpay.post("/authorise", json=AUTH).json()

    assert body["status"] == "DECLINED"
    assert body["provider_ref"] is None
    assert mockpay.get("/_control/outcome").json() == {"mode": "decline", "delay_ms": 0}


def test_timeout_outcome_answers_504_and_authorises_nothing(mockpay: TestClient) -> None:
    _set_outcome(mockpay, mode="timeout")

    assert mockpay.post("/authorise", json=AUTH).status_code == 504

    refund = {"reference": "ref-1", "auth_reference": "pay-1", "amount_paise": 8000}
    assert mockpay.post("/refund", json=refund).status_code == 409


def test_approve_after_a_delay(mockpay: TestClient) -> None:
    _set_outcome(mockpay, mode="approve", delay_ms=100)

    started = time.monotonic()
    body = mockpay.post("/authorise", json=AUTH).json()

    assert time.monotonic() - started >= 0.1
    assert body["status"] == "APPROVED"


def test_tc_us23_ac3_outcome_control_is_unavailable_in_production() -> None:
    mockpay = TestClient(create_app(Settings(env="production")))

    assert mockpay.put("/_control/outcome", json={"mode": "decline"}).status_code == 404
    assert mockpay.get("/_control/outcome").status_code == 404
    assert mockpay.post("/authorise", json=AUTH).json()["status"] == "APPROVED"


@pytest.mark.parametrize(
    "outcome",
    [{"mode": "explode"}, {"mode": "approve", "delay_ms": -1}, {"mode": "approve", "extra": 1}],
)
def test_invalid_outcome_gets_422(mockpay: TestClient, outcome: dict[str, object]) -> None:
    assert mockpay.put("/_control/outcome", json=outcome).status_code == 422


@pytest.mark.parametrize("amount", [0, -1])
def test_non_positive_amount_gets_422(mockpay: TestClient, amount: int) -> None:
    assert mockpay.post("/authorise", json={**AUTH, "amount_paise": amount}).status_code == 422


def test_void_cancels_an_approved_authorisation(mockpay: TestClient) -> None:
    mockpay.post("/authorise", json=AUTH)

    first = mockpay.post("/void", json={"reference": "pay-1"})
    second = mockpay.post("/void", json={"reference": "pay-1"})

    assert first.status_code == second.status_code == 200
    assert first.json()["status"] == second.json()["status"] == "VOIDED"
    refund = {"reference": "ref-1", "auth_reference": "pay-1", "amount_paise": 8000}
    assert mockpay.post("/refund", json=refund).status_code == 409


def test_void_before_the_authorisation_arrives_blocks_it(mockpay: TestClient) -> None:
    assert mockpay.post("/void", json={"reference": "pay-1"}).status_code == 200

    body = mockpay.post("/authorise", json=AUTH).json()

    assert body["status"] == "VOIDED"
    assert body["provider_ref"] is None


def test_void_of_a_declined_authorisation_changes_nothing(mockpay: TestClient) -> None:
    _set_outcome(mockpay, mode="decline")
    mockpay.post("/authorise", json=AUTH)

    response = mockpay.post("/void", json={"reference": "pay-1"})

    assert response.status_code == 200
    assert response.json()["status"] == "DECLINED"


def test_refund_is_recorded_once_per_reference(mockpay: TestClient) -> None:
    mockpay.post("/authorise", json=AUTH)
    refund = {"reference": "ref-1", "auth_reference": "pay-1", "amount_paise": 5000}

    first = mockpay.post("/refund", json=refund)
    second = mockpay.post("/refund", json=refund)

    assert first.status_code == second.status_code == 200
    assert first.json() == second.json() == refund
    # Only 3000 paise are left: the repeat did not refund a second 5000.
    rest = {"reference": "ref-2", "auth_reference": "pay-1", "amount_paise": 3000}
    assert mockpay.post("/refund", json=rest).status_code == 200
    over = {"reference": "ref-3", "auth_reference": "pay-1", "amount_paise": 1}
    assert mockpay.post("/refund", json=over).status_code == 409


def test_refund_reference_reused_for_another_refund_gets_409(mockpay: TestClient) -> None:
    mockpay.post("/authorise", json=AUTH)
    refund = {"reference": "ref-1", "auth_reference": "pay-1", "amount_paise": 5000}
    mockpay.post("/refund", json=refund)

    response = mockpay.post("/refund", json={**refund, "amount_paise": 100})

    assert response.status_code == 409


def test_refunded_authorisation_cannot_be_voided(mockpay: TestClient) -> None:
    mockpay.post("/authorise", json=AUTH)
    refund = {"reference": "ref-1", "auth_reference": "pay-1", "amount_paise": 5000}
    mockpay.post("/refund", json=refund)

    assert mockpay.post("/void", json={"reference": "pay-1"}).status_code == 409
