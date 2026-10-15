"""The guarded LLM client (CAFIITK-175): transaction guard, cache, breaker, daily cap.

The daily cap lives in PostgreSQL, so these tests use the real test database.
The OpenAI adapter is exercised over a mocked HTTP transport: no key, no network.
"""

import json
import threading
from collections.abc import Callable, Iterator
from datetime import datetime, timedelta

import httpx
import openai
import pytest
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.core import clock
from app.core.config import Settings
from app.modules.agent import client as client_module
from app.modules.agent.llm import (
    DAILY_BUDGET_SUBJECT,
    CircuitBreaker,
    GuardedLLMClient,
    LLMBudgetExceededError,
    LLMCalledInTransactionError,
    LLMProviderError,
    LLMRequest,
    LLMUnavailableError,
    Message,
    ResponseCache,
    ToolCall,
    ToolSpec,
)
from app.modules.agent.openai_provider import OpenAIProvider
from app.modules.agent.stub import StubProvider, reply

NOW = datetime(2026, 10, 15, 11, 30, tzinfo=clock.IST)
REQUEST = LLMRequest(messages=(Message("user", '{"inventory": [{"item": 1, "available": 4}]}'),))
OTHER_REQUEST = LLMRequest(messages=(Message("user", '{"inventory": []}'),))


@pytest.fixture
def sessions(engine: Engine) -> Iterator[sessionmaker[Session]]:
    yield sessionmaker(bind=engine)
    with engine.begin() as connection:
        connection.execute(
            text("DELETE FROM rate_limits WHERE subject = :s"), {"s": DAILY_BUDGET_SUBJECT}
        )


@pytest.fixture
def make_client(
    sessions: sessionmaker[Session],
) -> Iterator[Callable[..., GuardedLLMClient]]:
    opened: list[Session] = []

    def make(
        provider: StubProvider | None,
        *,
        daily_cap: int = 50,
        breaker: CircuitBreaker | None = None,
        cache: ResponseCache | None = None,
        now: Callable[[], datetime] = lambda: NOW,
    ) -> GuardedLLMClient:
        session = sessions()
        opened.append(session)
        return GuardedLLMClient(
            provider,
            session,
            daily_cap=daily_cap,
            breaker=breaker or CircuitBreaker(),
            cache=cache if cache is not None else ResponseCache(),
            now=now,
        )

    yield make
    for session in opened:
        session.close()


def _budget_used(engine: Engine) -> int:
    with engine.connect() as connection:
        used = connection.execute(
            text("SELECT coalesce(sum(count), 0) FROM rate_limits WHERE subject = :s"),
            {"s": DAILY_BUDGET_SUBJECT},
        ).scalar_one()
    return int(used)


def test_refuses_to_call_inside_a_transaction(sessions: sessionmaker[Session]) -> None:
    provider = StubProvider([reply("ok")])
    with sessions() as session, session.begin():
        llm = GuardedLLMClient(
            provider, session, daily_cap=5, breaker=CircuitBreaker(), cache=ResponseCache()
        )
        with pytest.raises(LLMCalledInTransactionError):
            llm.complete(REQUEST)
    assert provider.requests == []


def test_without_a_key_the_llm_is_unavailable_and_no_budget_is_used(
    make_client: Callable[..., GuardedLLMClient], engine: Engine
) -> None:
    with pytest.raises(LLMUnavailableError, match="no LLM API key"):
        make_client(None).complete(REQUEST)
    assert _budget_used(engine) == 0


def test_identical_request_is_served_from_the_cache(
    make_client: Callable[..., GuardedLLMClient], engine: Engine
) -> None:
    provider = StubProvider([reply("plan")])
    llm = make_client(provider)

    first = llm.complete(REQUEST)
    second = llm.complete(REQUEST)

    assert first.content == second.content == "plan"
    assert not first.cached
    assert second.cached
    assert len(provider.requests) == 1
    assert _budget_used(engine) == 1


def test_different_tool_data_calls_the_provider_again(
    make_client: Callable[..., GuardedLLMClient],
) -> None:
    provider = StubProvider([reply("a"), reply("b")])
    llm = make_client(provider)

    assert llm.complete(REQUEST).content == "a"
    assert llm.complete(OTHER_REQUEST).content == "b"
    assert len(provider.requests) == 2


def test_the_cache_does_not_carry_over_to_the_next_day(
    make_client: Callable[..., GuardedLLMClient],
) -> None:
    provider = StubProvider([reply("today"), reply("tomorrow")])
    cache = ResponseCache()
    make_client(provider, cache=cache).complete(REQUEST)

    tomorrow = make_client(provider, cache=cache, now=lambda: NOW + timedelta(days=1))

    assert tomorrow.complete(REQUEST).content == "tomorrow"


def test_the_daily_cap_stops_provider_calls(
    make_client: Callable[..., GuardedLLMClient], engine: Engine
) -> None:
    provider = StubProvider([reply(str(i)) for i in range(5)])
    llm = make_client(provider, daily_cap=2)
    llm.complete(REQUEST)
    llm.complete(OTHER_REQUEST)

    with pytest.raises(LLMBudgetExceededError):
        llm.complete(LLMRequest(messages=(Message("user", "third"),)))
    assert len(provider.requests) == 2
    assert _budget_used(engine) == 2


def test_a_cached_answer_is_still_given_after_the_cap(
    make_client: Callable[..., GuardedLLMClient],
) -> None:
    provider = StubProvider([reply("plan")])
    llm = make_client(provider, daily_cap=1)
    llm.complete(REQUEST)

    assert llm.complete(REQUEST).cached


def test_the_cap_is_shared_across_processes_and_holds_under_concurrency(
    make_client: Callable[..., GuardedLLMClient], engine: Engine
) -> None:
    # Separate clients and sessions stand in for separate processes (NFR-13).
    cap = 5
    provider = StubProvider([reply(str(i)) for i in range(20)])
    clients = [make_client(provider, daily_cap=cap) for _ in range(12)]
    outcomes: list[str] = []
    lock = threading.Lock()

    def call(index: int) -> None:
        request = LLMRequest(messages=(Message("user", f"request {index}"),))
        try:
            clients[index].complete(request)
            result = "ok"
        except LLMBudgetExceededError:
            result = "capped"
        with lock:
            outcomes.append(result)

    threads = [threading.Thread(target=call, args=(i,)) for i in range(len(clients))]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert outcomes.count("ok") == cap
    assert outcomes.count("capped") == len(clients) - cap
    assert _budget_used(engine) == cap


def test_provider_failure_is_reported_as_unavailable(
    make_client: Callable[..., GuardedLLMClient],
) -> None:
    llm = make_client(StubProvider([LLMProviderError("timeout")]))

    with pytest.raises(LLMUnavailableError, match="timeout"):
        llm.complete(REQUEST)


def test_the_breaker_opens_after_repeated_failures_and_recovers(
    make_client: Callable[..., GuardedLLMClient],
) -> None:
    clock_s = [0.0]
    breaker = CircuitBreaker(threshold=2, cooldown_s=60, monotonic=lambda: clock_s[0])
    provider = StubProvider([LLMProviderError("down"), LLMProviderError("down"), reply("back")])
    llm = make_client(provider, breaker=breaker)
    for _ in range(2):
        with pytest.raises(LLMUnavailableError):
            llm.complete(REQUEST)

    with pytest.raises(LLMUnavailableError, match="circuit breaker"):
        llm.complete(REQUEST)
    assert len(provider.requests) == 2

    clock_s[0] = 61.0
    assert llm.complete(REQUEST).content == "back"
    assert breaker.allow()


def test_a_failed_trial_reopens_the_breaker(
    make_client: Callable[..., GuardedLLMClient],
) -> None:
    clock_s = [0.0]
    breaker = CircuitBreaker(threshold=1, cooldown_s=60, monotonic=lambda: clock_s[0])
    llm = make_client(
        StubProvider([LLMProviderError("down"), LLMProviderError("still down")]),
        breaker=breaker,
    )
    with pytest.raises(LLMUnavailableError):
        llm.complete(REQUEST)
    clock_s[0] = 61.0
    with pytest.raises(LLMUnavailableError, match="still down"):
        llm.complete(REQUEST)

    assert not breaker.allow()


# --- OpenAI adapter over a mocked transport ---------------------------------

API_KEY = "sk-test-do-not-log-0123456789"


def _openai(handler: Callable[[httpx.Request], httpx.Response]) -> OpenAIProvider:
    client = openai.OpenAI(
        api_key=API_KEY,
        base_url="https://llm.test/v1",
        max_retries=0,
        timeout=1.0,
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    return OpenAIProvider(client, "gpt-test")


def _completion(message: dict[str, object]) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "id": "chatcmpl-1",
            "object": "chat.completion",
            "created": 0,
            "model": "gpt-test-2026",
            "choices": [{"index": 0, "finish_reason": "stop", "message": message}],
            "usage": {"prompt_tokens": 120, "completion_tokens": 30, "total_tokens": 150},
        },
    )


def test_openai_request_carries_messages_and_tools() -> None:
    seen: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return _completion({"role": "assistant", "content": "done"})

    tool = ToolSpec("get_inventory_levels", "Portions per item", {"type": "object"})
    earlier_call = ToolCall("call_1", "get_inventory_levels", "{}")
    request = LLMRequest(
        messages=(
            Message("system", "You plan the kitchen."),
            Message("assistant", None, tool_calls=(earlier_call,)),
            Message("tool", '{"items": []}', tool_call_id="call_1"),
        ),
        tools=(tool,),
    )

    response = _openai(handler).complete(request)

    body = seen[0]
    assert body["model"] == "gpt-test"
    assert body["tools"] == [
        {
            "type": "function",
            "function": {
                "name": "get_inventory_levels",
                "description": "Portions per item",
                "parameters": {"type": "object"},
            },
        }
    ]
    messages = body["messages"]
    assert isinstance(messages, list)
    assert messages[1]["tool_calls"][0]["function"]["name"] == "get_inventory_levels"
    assert messages[2] == {"role": "tool", "content": '{"items": []}', "tool_call_id": "call_1"}
    assert response.content == "done"
    assert (response.model, response.prompt_tokens, response.completion_tokens) == (
        "gpt-test-2026",
        120,
        30,
    )


def test_openai_tool_call_arguments_are_kept_raw_even_if_malformed() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return _completion(
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_9",
                        "type": "function",
                        "function": {"name": "propose_replenishment_plan", "arguments": "{oops"},
                    }
                ],
            }
        )

    response = _openai(handler).complete(REQUEST)

    assert response.tool_calls == (ToolCall("call_9", "propose_replenishment_plan", "{oops"),)


@pytest.mark.parametrize(
    "handler",
    [
        lambda request: httpx.Response(500, json={"error": {"message": "boom"}}),
        lambda request: httpx.Response(401, json={"error": {"message": f"bad key {API_KEY}"}}),
        lambda request: (_ for _ in ()).throw(httpx.ReadTimeout("slow", request=request)),
    ],
    ids=["server-error", "unauthorised", "timeout"],
)
def test_openai_failures_raise_provider_error_without_the_key(
    handler: Callable[[httpx.Request], httpx.Response],
) -> None:
    with pytest.raises(LLMProviderError) as raised:
        _openai(handler).complete(REQUEST)

    assert API_KEY not in str(raised.value)


def test_openai_reply_without_choices_is_a_provider_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "id": "x",
                "object": "chat.completion",
                "created": 0,
                "model": "m",
                "choices": [],
            },
        )

    with pytest.raises(LLMProviderError, match="no choices"):
        _openai(handler).complete(REQUEST)


# --- Settings and factory ----------------------------------------------------


def test_a_blank_key_means_no_key_and_a_set_key_is_hidden() -> None:
    assert Settings(llm_api_key="").llm_api_key is None
    settings = Settings(llm_api_key=API_KEY)
    assert API_KEY not in repr(settings)
    assert API_KEY not in str(settings.model_dump())


def test_factory_without_a_key_gives_an_unavailable_client(
    sessions: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("CAF_LLM_API_KEY", raising=False)
    monkeypatch.setattr(client_module, "get_settings", lambda: Settings(_env_file=None))
    client_module.get_provider.cache_clear()
    try:
        with sessions() as session, pytest.raises(LLMUnavailableError):
            client_module.get_llm_client(session).complete(REQUEST)
    finally:
        client_module.get_provider.cache_clear()


def test_factory_with_a_key_builds_the_openai_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        client_module,
        "get_settings",
        lambda: Settings(llm_api_key=API_KEY, llm_model="gpt-test", _env_file=None),
    )
    client_module.get_provider.cache_clear()
    try:
        provider = client_module.get_provider()
        assert isinstance(provider, OpenAIProvider)
        assert provider.model == "gpt-test"
    finally:
        client_module.get_provider.cache_clear()
