"""A scripted LLM provider for tests and CI: no network, no key, no cost."""

from collections.abc import Callable, Iterable

from app.modules.agent.llm import LLMProviderError, LLMRequest, LLMResponse

Reply = LLMResponse | Exception | Callable[[LLMRequest], LLMResponse]


def reply(content: str | None = None, **fields: object) -> LLMResponse:
    defaults: dict[str, object] = {
        "tool_calls": (),
        "model": "stub",
        "prompt_tokens": 10,
        "completion_tokens": 5,
        "latency_ms": 1,
    }
    return LLMResponse(content=content, **(defaults | fields))  # type: ignore[arg-type]


class StubProvider:
    """Answers each request with the next scripted reply; records every request."""

    model = "stub"

    def __init__(self, replies: Iterable[Reply] = ()) -> None:
        self._replies = list(replies)
        self.requests: list[LLMRequest] = []

    def complete(self, request: LLMRequest) -> LLMResponse:
        self.requests.append(request)
        if not self._replies:
            raise LLMProviderError("stub has no scripted reply left")
        next_reply = self._replies.pop(0)
        if isinstance(next_reply, Exception):
            raise next_reply
        if callable(next_reply):
            return next_reply(request)
        return next_reply
