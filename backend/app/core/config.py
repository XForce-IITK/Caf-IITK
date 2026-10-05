"""Deploy-time configuration, read from environment variables (NFR-24).

Administrator-configurable parameters (Table 4.0-B of the SRS) live in the
`settings` table instead, so they can change without a deployment (FR-23).
"""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CAF_", env_file=".env", extra="ignore")

    env: Literal["development", "test", "production"] = "development"
    database_url: str = "postgresql+psycopg://caf:caf@localhost:5432/caf"
    jwt_secret: str = "change-me-in-.env"
    mockpay_url: str = "http://localhost:8001"

    # Deploy-time parameters from Table 4.0-B
    pay_timeout_s: int = 10
    hold_expiry_s: int = 120
    sweep_interval_s: int = 30
    idem_ttl_h: int = 24
    access_ttl_min: int = 15
    refresh_ttl_days: int = 7

    @property
    def is_production(self) -> bool:
        return self.env == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
