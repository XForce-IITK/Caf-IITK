"""Deploy-time configuration, read from environment variables (NFR-24).

Administrator-configurable parameters (Table 4.0-B of the SRS) live in the
`settings` table instead, so they can change without a deployment (FR-23).
"""

from functools import lru_cache
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_JWT_SECRET = "change-me-in-.env"
# RFC 7518 3.2: an HS256 key should be at least as long as the hash output.
MIN_JWT_SECRET_BYTES = 32


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CAF_", env_file=".env", extra="ignore")

    env: Literal["development", "test", "production"] = "development"
    database_url: str = "postgresql+psycopg://caf:caf@localhost:5432/caf"
    jwt_secret: str = DEFAULT_JWT_SECRET
    mockpay_url: str = "http://localhost:8001"

    # Deploy-time parameters from Table 4.0-B
    pay_timeout_s: int = 10
    hold_expiry_s: int = 120
    sweep_interval_s: int = 30
    idem_ttl_h: int = 24
    access_ttl_min: int = 15
    refresh_ttl_days: int = 7

    # Deployment-time seed accounts (FR-2); see app/seed.py. Unset means not seeded.
    seed_admin_email: str | None = None
    seed_admin_password: str | None = None
    seed_kitchen_email: str | None = None
    seed_kitchen_password: str | None = None

    @model_validator(mode="after")
    def _require_strong_jwt_secret_in_production(self) -> "Settings":
        if self.is_production and (
            self.jwt_secret == DEFAULT_JWT_SECRET
            or len(self.jwt_secret.encode()) < MIN_JWT_SECRET_BYTES
        ):
            raise ValueError(f"CAF_JWT_SECRET must be set to at least {MIN_JWT_SECRET_BYTES} bytes")
        return self

    @property
    def is_production(self) -> bool:
        return self.env == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
