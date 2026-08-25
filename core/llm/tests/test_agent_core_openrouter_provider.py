"""Integration tests for `OpenRouterProvider` against a mocked `httpx` transport.

No network: every response is built by an `httpx.MockTransport` handler
and streamed back exactly as `httpx.AsyncClient` would deliver it over
the wire, including the lazy body a 4xx/5xx response needs `aread()`
for before its JSON is available.
"""

import json
import unittest
from typing import AsyncIterator, List

import httpx

from llm.agent_core.events import ToolCall, ToolCallFunction
from llm.agent_core.openrouter_provider import CHAT_COMPLETIONS_PATH, DEFAULT_BASE_URL, OpenRouterProvider
from llm.agent_core.provider import (
    ChatCompletionRequest,
    ProviderContentDeltaChunk,
    ProviderDoneChunk,
    ProviderGenerationIdChunk,
    ProviderMessage,
    ProviderToolCallDeltaChunk,
    ProviderUsageChunk,
    ToolDefinition,
    ToolFunctionDefinition,
)
from llm.agent_core.provider_errors import (
    ProviderAuthError,
    ProviderError,
    ProviderOverloadedError,
    ProviderRateLimitError,
    ProviderTransportError,
)


def _sse_body(*data_payloads: str) -> AsyncIterator[bytes]:
    """An async byte stream shaped like a real streamed SSE response body.

    Yielding one chunk per SSE event (rather than handing the whole
    body as one `bytes` blob) is what makes `httpx` treat the response
    as unread until `aread()`/iteration actually consumes it -- the
    same lazy-body behavior a real streamed HTTP response has.
    """
    async def _gen():
        for payload in data_payloads:
            yield f"data: {payload}\n\n".encode()
        yield b"data: [DONE]\n\n"

    return _gen()


def _error_body(payload: dict) -> AsyncIterator[bytes]:
    async def _gen():
        yield json.dumps(payload).encode()

    return _gen()


def _request() -> ChatCompletionRequest:
    return ChatCompletionRequest(model="fixture/model", messages=[ProviderMessage(role="user", content="hi")])


class OpenRouterProviderStreamingTests(unittest.IsolatedAsyncioTestCase):
    async def _collect(self, transport: httpx.MockTransport) -> List:
        async with httpx.AsyncClient(transport=transport) as client:
            provider = OpenRouterProvider("sk-test", client)
            return [chunk async for chunk in provider.stream_chat(_request())]

    async def test_happy_stream_yields_generation_id_then_content_then_done(self):
        def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.url.path, f"{httpx.URL(DEFAULT_BASE_URL).path}{CHAT_COMPLETIONS_PATH}")
            self.assertEqual(request.headers["authorization"], "Bearer sk-test")
            return httpx.Response(
                200,
                content=_sse_body(
                    json.dumps({"id": "gen-1", "choices": [{"delta": {"role": "assistant"}, "finish_reason": None}]}),
                    json.dumps({"id": "gen-1", "choices": [{"delta": {"content": "Hello"}, "finish_reason": None}]}),
                    json.dumps({"id": "gen-1", "choices": [{"delta": {}, "finish_reason": "stop"}]}),
                ),
            )

        chunks = await self._collect(httpx.MockTransport(handler))

        self.assertEqual(chunks[0], ProviderGenerationIdChunk(generation_id="gen-1"))
        self.assertEqual(chunks[1], ProviderContentDeltaChunk(content="Hello"))
        self.assertEqual(chunks[2], ProviderDoneChunk(finish_reason="stop"))

    async def test_generation_id_is_emitted_only_once_across_the_stream(self):
        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                content=_sse_body(
                    json.dumps({"id": "gen-1", "choices": [{"delta": {"content": "A"}, "finish_reason": None}]}),
                    json.dumps({"id": "gen-1", "choices": [{"delta": {"content": "B"}, "finish_reason": None}]}),
                ),
            )

        chunks = await self._collect(httpx.MockTransport(handler))
        generation_id_chunks = [c for c in chunks if isinstance(c, ProviderGenerationIdChunk)]
        self.assertEqual(len(generation_id_chunks), 1)

    async def test_tool_call_stream_yields_indexed_deltas(self):
        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                content=_sse_body(
                    json.dumps(
                        {
                            "id": "gen-2",
                            "choices": [
                                {
                                    "delta": {
                                        "tool_calls": [
                                            {
                                                "index": 0,
                                                "id": "call-1",
                                                "function": {"name": "brave_web_search", "arguments": ""},
                                            }
                                        ]
                                    },
                                    "finish_reason": None,
                                }
                            ],
                        }
                    ),
                    json.dumps(
                        {
                            "id": "gen-2",
                            "choices": [
                                {
                                    "delta": {
                                        "tool_calls": [{"index": 0, "function": {"arguments": '{"query": "sterna"}'}}]
                                    },
                                    "finish_reason": None,
                                }
                            ],
                        }
                    ),
                    json.dumps({"id": "gen-2", "choices": [{"delta": {}, "finish_reason": "tool_calls"}]}),
                ),
            )

        chunks = await self._collect(httpx.MockTransport(handler))
        tool_call_chunks = [c for c in chunks if isinstance(c, ProviderToolCallDeltaChunk)]

        self.assertEqual(tool_call_chunks[0], ProviderToolCallDeltaChunk(index=0, id="call-1", name="brave_web_search", arguments_delta=""))
        self.assertEqual(tool_call_chunks[1], ProviderToolCallDeltaChunk(index=0, id=None, name=None, arguments_delta='{"query": "sterna"}'))
        self.assertEqual(chunks[-1], ProviderDoneChunk(finish_reason="tool_calls"))

    async def test_usage_is_extracted_from_the_final_chunk(self):
        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                content=_sse_body(
                    json.dumps({"id": "gen-3", "choices": [{"delta": {"content": "hi"}, "finish_reason": None}]}),
                    json.dumps(
                        {
                            "id": "gen-3",
                            "choices": [{"delta": {}, "finish_reason": "stop"}],
                            "usage": {
                                "prompt_tokens": 120,
                                "completion_tokens": 40,
                                "total_tokens": 160,
                                "cost": 0.00032,
                                "cost_details": {"upstream_inference_cost": 0.00025},
                            },
                        }
                    ),
                ),
            )

        chunks = await self._collect(httpx.MockTransport(handler))
        usage_chunks = [c for c in chunks if isinstance(c, ProviderUsageChunk)]

        self.assertEqual(len(usage_chunks), 1)
        usage_chunk = usage_chunks[0]
        self.assertEqual(usage_chunk.usage.prompt_tokens, 120)
        self.assertEqual(usage_chunk.usage.total_tokens, 160)
        self.assertEqual(usage_chunk.cost, 0.00032)
        self.assertEqual(usage_chunk.upstream_inference_cost, 0.00025)

    async def test_mid_stream_error_payload_raises_a_mapped_provider_error(self):
        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                content=_sse_body(
                    json.dumps({"id": "gen-4", "choices": [{"delta": {"content": "partial"}, "finish_reason": None}]}),
                    json.dumps({"error": {"code": 503, "message": "Provider returned error"}}),
                ),
            )

        transport = httpx.MockTransport(handler)
        collected = []
        with self.assertRaises(ProviderOverloadedError) as ctx:
            async with httpx.AsyncClient(transport=transport) as client:
                provider = OpenRouterProvider("sk-test", client)
                async for chunk in provider.stream_chat(_request()):
                    collected.append(chunk)

        self.assertEqual(collected, [ProviderGenerationIdChunk(generation_id="gen-4"), ProviderContentDeltaChunk(content="partial")])
        self.assertEqual(ctx.exception.status_code, 503)
        self.assertIsInstance(ctx.exception, ProviderError)

    async def test_429_response_raises_rate_limit_error_with_retry_after(self):
        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                429,
                headers={"Retry-After": "17"},
                content=_error_body({"error": {"message": "Rate limit exceeded", "code": 429}}),
            )

        with self.assertRaises(ProviderRateLimitError) as ctx:
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
                provider = OpenRouterProvider("sk-test", client)
                async for _chunk in provider.stream_chat(_request()):
                    pass

        self.assertEqual(ctx.exception.status_code, 429)
        self.assertEqual(ctx.exception.retry_after, 17.0)
        self.assertIn("Rate limit exceeded", ctx.exception.message)

    async def test_401_response_raises_auth_error(self):
        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                401,
                content=_error_body({"error": {"message": "Missing Authentication header"}}),
            )

        with self.assertRaises(ProviderAuthError) as ctx:
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
                provider = OpenRouterProvider("sk-test", client)
                async for _chunk in provider.stream_chat(_request()):
                    pass

        self.assertEqual(ctx.exception.status_code, 401)

    async def test_string_status_code_in_mid_stream_error_is_coerced(self):
        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                content=_sse_body(json.dumps({"error": {"code": "429", "message": "Rate limit exceeded"}})),
            )

        with self.assertRaises(ProviderRateLimitError) as ctx:
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
                provider = OpenRouterProvider("sk-test", client)
                async for _chunk in provider.stream_chat(_request()):
                    pass

        self.assertEqual(ctx.exception.status_code, 429)

    async def test_malformed_json_chunk_is_skipped_not_raised(self):
        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                content=_sse_body(
                    "{not valid json",
                    json.dumps({"id": "gen-5", "choices": [{"delta": {"content": "hi"}, "finish_reason": None}]}),
                ),
            )

        chunks = await self._collect(httpx.MockTransport(handler))

        self.assertEqual(chunks, [ProviderGenerationIdChunk(generation_id="gen-5"), ProviderContentDeltaChunk(content="hi")])

    async def test_connect_failure_raises_provider_transport_error(self):
        def handler(_request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused")

        with self.assertRaises(ProviderTransportError):
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
                provider = OpenRouterProvider("sk-test", client)
                async for _chunk in provider.stream_chat(_request()):
                    pass

    async def test_mid_stream_disconnect_raises_provider_transport_error(self):
        async def body():
            yield b'data: {"id": "gen-6", "choices": [{"delta": {"content": "partial"}}]}\n\n'
            raise httpx.ReadError("connection reset")

        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=body())

        collected = []
        with self.assertRaises(ProviderTransportError):
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
                provider = OpenRouterProvider("sk-test", client)
                async for chunk in provider.stream_chat(_request()):
                    collected.append(chunk)

        self.assertEqual(
            collected,
            [ProviderGenerationIdChunk(generation_id="gen-6"), ProviderContentDeltaChunk(content="partial")],
        )


class OpenRouterProviderOutboundPayloadTests(unittest.IsolatedAsyncioTestCase):
    async def test_request_body_serializes_tools_and_tool_call_history(self):
        captured: List[bytes] = []

        def handler(request: httpx.Request) -> httpx.Response:
            captured.append(request.content)
            return httpx.Response(200, content=_sse_body())

        request = ChatCompletionRequest(
            model="fixture/model",
            messages=[
                ProviderMessage(role="user", content="search sterna"),
                ProviderMessage(
                    role="assistant",
                    content=None,
                    tool_calls=[
                        ToolCall(
                            id="call-1",
                            function=ToolCallFunction(name="brave_web_search", arguments='{"query": "sterna"}'),
                        )
                    ],
                ),
                ProviderMessage(role="tool", content="[]", tool_call_id="call-1", name="brave_web_search"),
            ],
            tools=[
                ToolDefinition(
                    function=ToolFunctionDefinition(
                        name="brave_web_search",
                        description="Search the web.",
                        parameters={"type": "object", "properties": {"query": {"type": "string"}}},
                    )
                )
            ],
            tool_choice="auto",
        )

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = OpenRouterProvider("sk-test", client)
            async for _chunk in provider.stream_chat(request):
                pass

        body = json.loads(captured[0])

        self.assertEqual(body["model"], "fixture/model")
        self.assertIs(body["stream"], True)
        self.assertNotIn("temperature", body)
        self.assertNotIn("max_tokens", body)
        self.assertEqual(body["tool_choice"], "auto")
        self.assertEqual(
            body["tools"],
            [
                {
                    "type": "function",
                    "function": {
                        "name": "brave_web_search",
                        "description": "Search the web.",
                        "parameters": {"type": "object", "properties": {"query": {"type": "string"}}},
                    },
                }
            ],
        )
        self.assertEqual(body["messages"][0], {"role": "user", "content": "search sterna"})
        self.assertEqual(
            body["messages"][1],
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": "call-1",
                        "type": "function",
                        "function": {"name": "brave_web_search", "arguments": '{"query": "sterna"}'},
                    }
                ],
            },
        )
        self.assertEqual(
            body["messages"][2],
            {"role": "tool", "content": "[]", "tool_call_id": "call-1", "name": "brave_web_search"},
        )


if __name__ == "__main__":
    unittest.main()
