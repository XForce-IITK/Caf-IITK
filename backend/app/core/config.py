"""Deploy-time configuration, read from environment variables (NFR-24).

Administrator-configurable parameters (Table 4.0-B of the SRS) live in the
`settings` table instead, so they can change without a deployment (FR-23).
"""

from functools import lru_cache
from typing import Literal

from pydantic import SecretStr, field_validator, model_validator
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
    # How long mockpay holds an authorisation in "timeout" mode; keep above pay_timeout_s.
    mockpay_hang_s: float = 30.0

    # Browser origins allowed to call the API (NFR-27), as a JSON list, e.g.
    # CAF_CORS_ORIGINS='["https://caf.example.org"]'. Outside production any
    # localhost port is also allowed, so `flutter run -d chrome` works.
    cors_origins: list[str] = []

    # Deploy-time parameters from Table 4.0-B
    pay_timeout_s: int = 10
    hold_expiry_s: int = 120
    sweep_interval_s: int = 30
    idem_ttl_h: int = 24
    access_ttl_min: int = 15
    refresh_ttl_days: int = 7

    # LLM for the Kitchen Planning Agent (OpenAI). Without a key every run uses the
    # heuristic planner (FR-59). The key is a SecretStr, so it never appears in a repr.
    llm_api_key: SecretStr | None = None
    llm_model: str = "gpt-4o-mini"
    llm_base_url: str | None = None
    llm_timeout_s: float = 20.0  # P-LLM_TIMEOUT
    agent_daily_cap: int = 50  # P-AGENT_DAILY_CAP
    agent_max_calls: int = 20  # P-AGENT_MAX_CALLS, tool calls per run
    agent_run_timeout_s: float = 60.0  # P-AGENT_RUN_TIMEOUT
    llm_breaker_threshold: int = 3
    llm_breaker_cooldown_s: float = 60.0

    # Deployment-time seed accounts (FR-2); see app/seed.py. Unset means not seeded.
    seed_admin_email: str | None = None
    seed_admin_password: str | None = None
    seed_kitchen_email: str | None = None
    seed_kitchen_password: str | None = None

    @field_validator("llm_api_key", mode="before")
    @classmethod
    def _blank_key_means_none(cls, value: object) -> object:
        # Docker Compose passes an unset key as an empty string.
        return None if value == "" else value

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
