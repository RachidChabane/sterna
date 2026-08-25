"""httpx-based `ModelProvider` adapter for the OpenRouter chat-completions API.

Speaks the wire format directly over SSE rather than through an SDK
or a LangChain chat-model wrapper, so nothing about the OpenRouter
generation id, tool-call deltas, or usage accounting depends on an
intermediate library's chunk shape — including the generation id,
which a raw chunk carries in its own `id` field and needs no
after-the-fact patching to preserve.
"""

from __future__ import annotations

import json
from typing import Any, AsyncIterator, Dict, Optional

import httpx

from .provider import (
    ChatCompletionRequest,
    ModelProvider,
    ProviderChunk,
    ProviderGenerationIdChunk,
    ProviderMessage,
    ToolDefinition,
)
from .provider_errors import ProviderError, ProviderResponseError, ProviderTransportError, map_status_to_error
from .sse_parsing import DONE_MARKER, extract_stream_error, parse_stream_chunk, sse_payload

DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
CHAT_COMPLETIONS_PATH = "/chat/completions"
_RETRY_AFTER_HEADER = "Retry-After"


class OpenRouterProvider(ModelProvider):
    """Streams chat completions from OpenRouter over an injected `httpx.AsyncClient`.

    The caller owns the client's lifecycle (creation and closing); the
    adapter only issues requests against it, so one client can be
    shared across many `OpenRouterProvider` instances or swapped for
    a test double.
    """

    def __init__(
        self,
        api_key: str,
        http_client: httpx.AsyncClient,
        *,
        base_url: str = DEFAULT_BASE_URL,
    ) -> None:
        self._api_key = api_key
        self._client = http_client
        self._base_url = base_url.rstrip("/")

    async def stream_chat(self, request: ChatCompletionRequest) -> AsyncIterator[ProviderChunk]:
        payload = _build_payload(request)

        try:
            async with self._client.stream(
                "POST",
                f"{self._base_url}{CHAT_COMPLETIONS_PATH}",
                json=payload,
                headers=self._headers(),
            ) as response:
                if response.status_code >= 400:
                    raise await _error_from_response(response)

                generation_id_emitted = False
                async for line in response.aiter_lines():
                    payload_text = sse_payload(line)
                    if payload_text is None:
                        continue
                    if payload_text.strip() == DONE_MARKER:
                        return

                    raw = _decode_chunk(payload_text)
                    if raw is None:
                        continue

                    stream_error = extract_stream_error(raw)
                    if stream_error is not None:
                        raise _error_from_stream_payload(stream_error)

                    for chunk in parse_stream_chunk(raw):
                        if isinstance(chunk, ProviderGenerationIdChunk):
                            if generation_id_emitted:
                                continue
                            generation_id_emitted = True
                        yield chunk
        except httpx.TransportError as exc:
            raise ProviderTransportError(str(exc) or exc.__class__.__name__) from exc

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }


def _build_payload(request: ChatCompletionRequest) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "model": request.model,
        "messages": [_serialize_message(message) for message in request.messages],
        "stream": True,
    }
    if request.tools:
        payload["tools"] = [_serialize_tool(tool) for tool in request.tools]
    if request.tool_choice is not None:
        payload["tool_choice"] = request.tool_choice
    if request.temperature is not None:
        payload["temperature"] = request.temperature
    if request.max_tokens is not None:
        payload["max_tokens"] = request.max_tokens
    if request.extra:
        payload.update(request.extra)
    return payload


def _serialize_message(message: ProviderMessage) -> Dict[str, Any]:
    serialized: Dict[str, Any] = {"role": message.role}
    if message.content is not None:
        serialized["content"] = message.content
    if message.tool_calls:
        serialized["tool_calls"] = [
            {
                "id": call.id,
                "type": call.type,
                "function": {"name": call.function.name, "arguments": call.function.arguments},
            }
            for call in message.tool_calls
        ]
    if message.tool_call_id is not None:
        serialized["tool_call_id"] = message.tool_call_id
    if message.name is not None:
        serialized["name"] = message.name
    return serialized


def _serialize_tool(tool: ToolDefinition) -> Dict[str, Any]:
    return {
        "type": tool.type,
        "function": {
            "name": tool.function.name,
            "description": tool.function.description,
            "parameters": tool.function.parameters,
        },
    }


async def _error_from_response(response: httpx.Response) -> ProviderError:
    retry_after = _parse_retry_after(response.headers.get(_RETRY_AFTER_HEADER))
    body = await response.aread()
    message = _extract_error_message(body) or response.reason_phrase or f"HTTP {response.status_code}"
    return map_status_to_error(response.status_code, message, retry_after=retry_after)


def _error_from_stream_payload(error: Dict[str, Any]) -> ProviderError:
    message = error.get("message") or "The provider reported a mid-stream error."
    status_code = _coerce_status_code(error.get("code"))
    if status_code is not None:
        return map_status_to_error(status_code, message)
    return ProviderResponseError(message)


def _coerce_status_code(code: Any) -> Optional[int]:
    if isinstance(code, bool):
        return None
    if isinstance(code, int):
        return code
    if isinstance(code, str):
        try:
            return int(code)
        except ValueError:
            return None
    return None


def _decode_chunk(payload_text: str) -> Optional[Dict[str, Any]]:
    try:
        return json.loads(payload_text)
    except json.JSONDecodeError:
        return None


def _extract_error_message(body: bytes) -> Optional[str]:
    try:
        parsed = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    error = parsed.get("error") if isinstance(parsed, dict) else None
    if isinstance(error, dict):
        return error.get("message")
    return None


def _parse_retry_after(value: Optional[str]) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None
