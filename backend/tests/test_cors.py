"""NFR-27: browsers may call the API only from the client's origin."""

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import create_app

PREFLIGHT = {
    "Access-Control-Request-Method": "POST",
    "Access-Control-Request-Headers": "authorization,content-type,idempotency-key,x-request-id",
}


@pytest.fixture
def production(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("CAF_ENV", "production")
    monkeypatch.setenv("CAF_JWT_SECRET", "p" * 40)
    monkeypatch.setenv("CAF_CORS_ORIGINS", '["https://caf.example.org"]')
    get_settings.cache_clear()
    client = TestClient(create_app())
    get_settings.cache_clear()
    return client


def _allowed_origin(client: TestClient, origin: str) -> str | None:
    response = client.options("/api/v1/orders", headers={"Origin": origin, **PREFLIGHT})
    origin_header: str | None = response.headers.get("access-control-allow-origin")
    return origin_header


def test_any_localhost_port_is_allowed_in_development() -> None:
    client = TestClient(create_app())

    assert _allowed_origin(client, "http://localhost:54321") == "http://localhost:54321"
    assert _allowed_origin(client, "http://127.0.0.1:8080") == "http://127.0.0.1:8080"
    assert _allowed_origin(client, "https://evil.example.org") is None
    assert _allowed_origin(client, "http://localhost.evil.example.org") is None


def test_preflight_allows_the_headers_the_client_sends() -> None:
    client = TestClient(create_app())
    response = client.options(
        "/api/v1/orders", headers={"Origin": "http://localhost:3000", **PREFLIGHT}
    )

    assert response.status_code == 200
    allowed = response.headers["access-control-allow-headers"].lower()
    for header in ("authorization", "content-type", "idempotency-key", "x-request-id"):
        assert header in allowed


def test_retry_after_is_readable_by_the_browser() -> None:
    client = TestClient(create_app())
    response = client.get("/health", headers={"Origin": "http://localhost:3000"})

    assert response.headers["access-control-expose-headers"] == "Retry-After"


def test_production_allows_only_the_configured_origin(production: TestClient) -> None:
    assert _allowed_origin(production, "https://caf.example.org") == "https://caf.example.org"
    assert _allowed_origin(production, "http://localhost:54321") is None
    assert _allowed_origin(production, "https://evil.example.org") is None
