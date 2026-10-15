"""OpenAI Chat Completions adapter for the LLM client (native tool calling)."""

import time
from typing import Any

import openai

from app.modules.agent.llm import LLMProviderError, LLMRequest, LLMResponse, Message, ToolCall


def _message(message: Message) -> dict[str, Any]:
    out: dict[str, Any] = {"role": message.role, "content": message.content}
    if message.tool_calls:
        out["tool_calls"] = [
            {
                "id": call.id,
                "type": "function",
                "function": {"name": call.name, "arguments": call.arguments},
            }
            for call in message.tool_calls
        ]
    if message.tool_call_id is not None:
        out["tool_call_id"] = message.tool_call_id
    return out


class OpenAIProvider:
    def __init__(self, client: openai.OpenAI, model: str) -> None:
        # The client carries the API key and P-LLM_TIMEOUT; retries are disabled so the
        # timeout bounds the whole call and failures reach the circuit breaker.
        self._client = client
        self.model = model

    def complete(self, request: LLMRequest) -> LLMResponse:
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": [_message(m) for m in request.messages],
        }
        if request.tools:
            kwargs["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.parameters,
                    },
                }
                for tool in request.tools
            ]
        started = time.monotonic()
        try:
            completion = self._client.chat.completions.create(**kwargs)
        except openai.OpenAIError as exc:
            # The exception text never contains the API key; only the class and status are kept.
            raise LLMProviderError(f"OpenAI request failed: {type(exc).__name__}") from exc
        latency_ms = int((time.monotonic() - started) * 1000)
        if not completion.choices:
            raise LLMProviderError("OpenAI returned no choices")
        reply = completion.choices[0].message
        tool_calls = tuple(
            ToolCall(id=call.id, name=call.function.name, arguments=call.function.arguments)
            for call in reply.tool_calls or ()
            if call.type == "function"
        )
        usage = completion.usage
        return LLMResponse(
            content=reply.content,
            tool_calls=tool_calls,
            model=completion.model,
            prompt_tokens=usage.prompt_tokens if usage else None,
            completion_tokens=usage.completion_tokens if usage else None,
            latency_ms=latency_ms,
        )
