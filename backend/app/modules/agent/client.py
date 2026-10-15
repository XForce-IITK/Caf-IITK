"""Builds the guarded LLM client from deploy-time settings."""

from functools import lru_cache

import openai
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.modules.agent.llm import CircuitBreaker, GuardedLLMClient, LLMProvider, ResponseCache
from app.modules.agent.openai_provider import OpenAIProvider


@lru_cache
def get_provider() -> LLMProvider | None:
    settings = get_settings()
    if settings.llm_api_key is None:
        return None
    client = openai.OpenAI(
        api_key=settings.llm_api_key.get_secret_value(),
        base_url=settings.llm_base_url,
        timeout=settings.llm_timeout_s,
        max_retries=0,
    )
    return OpenAIProvider(client, settings.llm_model)


# Shared by every run in this process, so the breaker and cache outlive one run.
@lru_cache
def get_breaker() -> CircuitBreaker:
    settings = get_settings()
    return CircuitBreaker(settings.llm_breaker_threshold, settings.llm_breaker_cooldown_s)


@lru_cache
def get_cache() -> ResponseCache:
    return ResponseCache()


def get_llm_client(session: Session) -> GuardedLLMClient:
    """The client for one agent run; `session` is the run's caf_app session."""
    return GuardedLLMClient(
        get_provider(),
        session,
        daily_cap=get_settings().agent_daily_cap,
        breaker=get_breaker(),
        cache=get_cache(),
    )
