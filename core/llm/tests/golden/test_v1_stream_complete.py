"""Golden SSE transcripts for the V1 streaming loop.

`CompletionViewSet.stream_complete` owns its tool loop inline: it reads
provider chunks, splits the tool calls a `done` event carries into file
tools (executed immediately, then the model is recalled) and everything
else (gated behind an MCP approval, which ends the stream), and frames
each result as an SSE event.

The provider is replaced by `FakeOpenRouterClient`, which replays a fixed
list of chunks per call, so the transcript depends only on the loop.
"""

import json
from unittest.mock import patch

import pytest
from rest_framework.test import APIClient, APITestCase

from llm.tests.conftest import make_billing_user, seed_billing_plan
from llm.tests.golden.harness import (
    BILLING_PLAN_NAME,
    CATALOG_TOOL_CALL_ID,
    CATALOG_TOOL_NAME,
    CONVERSATION_ID,
    FILE_TOOL_CALL_ID,
    FILE_TOOL_NAME,
    FOLLOW_UP_GENERATION_ID,
    GENERATION_ID,
    MODEL_ID,
    PROVIDER_ERROR_MESSAGE,
    assert_matches_golden,
    assert_stream_is_substantive,
    capture_sse,
    seed_model_catalog,
)

pytestmark = pytest.mark.golden

STREAM_URL = "/api/llm/completions/stream-complete/"

FILE_TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": FILE_TOOL_NAME,
            "description": "Read a file from the workspace.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
    }
]

FILE_TOOL_ARGUMENTS = json.dumps({"path": "/workspace/notes.md"})
CATALOG_TOOL_ARGUMENTS = json.dumps({"query": "sterna streaming"})

FILE_TOOL_RESULTS = [
    {
        "role": "tool",
        "tool_call_id": FILE_TOOL_CALL_ID,
        "name": FILE_TOOL_NAME,
        "content": json.dumps({"success": True, "content": "# Notes\nfirst line\n"}),
    }
]


class FakeOpenRouterClient:
    """Provider stand-in whose `complete_stream` replays queued chunks.

    One queued list per call, mirroring one iteration of the V1 loop:
    the first call answers the user, a second answers the tool results.
    """

    def __init__(self, *_args, **_kwargs):
        self.calls = []

    def queue(self, *iteration_chunks):
        self._iterations = list(iteration_chunks)
        return self

    def complete_stream(self, **kwargs):
        self.calls.append(kwargs)
        chunks = self._iterations.pop(0) if self._iterations else []
        return iter(chunks)


class NoWaitRateLimiter:
    """Rate limiter stand-in: the real one sleeps against a shared cache."""

    def wait_if_needed(self, *_args, **_kwargs):
        return None


def content_chunk(text):
    return {"event": "content", "data": {"content": text}}


def generation_id_chunk(generation_id):
    return {"event": "generation_id", "data": {"generation_id": generation_id}}


def done_chunk(
    *,
    finish_reason="stop",
    tool_calls=None,
    prompt_tokens=120,
    completion_tokens=40,
    cost=0.00032,
    prompt_cost=0.00012,
    completion_cost=0.0002,
):
    data = {
        "model": MODEL_ID,
        "finish_reason": finish_reason,
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        },
        "cost": cost,
        "prompt_cost": prompt_cost,
        "completion_cost": completion_cost,
    }
    if tool_calls is not None:
        data["tool_calls"] = tool_calls
    return {"event": "done", "data": data}


def tool_call(call_id, name, arguments):
    return {
        "id": call_id,
        "type": "function",
        "function": {"name": name, "arguments": arguments},
    }


def failing_stream(chunks, message):
    """Chunks followed by an upstream failure, as a generator would raise."""

    def _generator():
        for chunk in chunks:
            yield chunk
        raise RuntimeError(message)

    return _generator()


class V1StreamCompleteGoldenTests(APITestCase):
    """Byte-exact transcripts of `CompletionViewSet.stream_complete`."""

    def setUp(self):
        seed_model_catalog()
        plan = seed_billing_plan(BILLING_PLAN_NAME)
        self.user = make_billing_user("v1-golden@example.com", plan)
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.provider = FakeOpenRouterClient()

    def _post(self, **overrides):
        payload = {
            "model": MODEL_ID,
            "messages": [{"role": "user", "content": "Summarize the notes."}],
            "temperature": 0.2,
            "max_tokens": 256,
            "top_p": 1.0,
            "conversation_id": CONVERSATION_ID,
        }
        payload.update(overrides)
        with patch("llm.views.OpenRouterClient", return_value=self.provider), \
                patch("llm.views.RateLimiter", NoWaitRateLimiter):
            response = self.client.post(STREAM_URL, payload, format="json")
            return capture_sse(response)

    # --- (a) plain streamed text --------------------------------------

    def test_plain_text_completion_transcript(self):
        self.provider.queue([
            generation_id_chunk(GENERATION_ID),
            content_chunk("The notes "),
            content_chunk("list two "),
            content_chunk("open items."),
            done_chunk(),
        ])

        raw = self._post()

        assert_stream_is_substantive(self, raw, ["generation_id", "content", "done"])
        assert_matches_golden(self, "v1_plain_text_completion", raw)

    # --- (b) tool-call round trips ------------------------------------

    def test_file_tool_round_trip_transcript(self):
        self.provider.queue(
            [
                generation_id_chunk(GENERATION_ID),
                content_chunk("Reading the file."),
                done_chunk(
                    finish_reason="tool_calls",
                    tool_calls=[tool_call(FILE_TOOL_CALL_ID, FILE_TOOL_NAME, FILE_TOOL_ARGUMENTS)],
                ),
            ],
            [
                generation_id_chunk(FOLLOW_UP_GENERATION_ID),
                content_chunk("The notes "),
                content_chunk("open with a heading."),
                done_chunk(prompt_tokens=200, completion_tokens=25, cost=0.00025),
            ],
        )

        with patch("llm.views.get_file_tools", return_value=FILE_TOOL_DEFINITIONS), \
                patch("llm.views.handle_file_tool_calls", return_value=FILE_TOOL_RESULTS):
            raw = self._post(enable_file_tools=True)

        assert_stream_is_substantive(
            self, raw, ["generation_id", "content", "file_tool_executed", "done"]
        )
        assert_matches_golden(self, "v1_file_tool_round_trip", raw)

    def test_catalog_tool_approval_gate_transcript(self):
        mcp_tool = self._seed_mcp_tool()
        self.provider.queue([
            generation_id_chunk(GENERATION_ID),
            content_chunk("Searching the web."),
            done_chunk(
                finish_reason="tool_calls",
                tool_calls=[
                    tool_call(CATALOG_TOOL_CALL_ID, CATALOG_TOOL_NAME, CATALOG_TOOL_ARGUMENTS)
                ],
            ),
        ])

        with self._patched_mcp_registry([mcp_tool]):
            raw = self._post(enable_mcp_tools=True)

        assert_stream_is_substantive(self, raw, ["tool_call_request", "done"])
        assert_matches_golden(self, "v1_catalog_tool_approval_gate", raw)

    def test_file_and_catalog_tools_in_one_turn_transcript(self):
        mcp_tool = self._seed_mcp_tool()
        self.provider.queue([
            generation_id_chunk(GENERATION_ID),
            content_chunk("Reading the file and searching the web."),
            done_chunk(
                finish_reason="tool_calls",
                tool_calls=[
                    tool_call(FILE_TOOL_CALL_ID, FILE_TOOL_NAME, FILE_TOOL_ARGUMENTS),
                    tool_call(CATALOG_TOOL_CALL_ID, CATALOG_TOOL_NAME, CATALOG_TOOL_ARGUMENTS),
                ],
            ),
        ])

        with self._patched_mcp_registry([mcp_tool]), \
                patch("llm.views.get_file_tools", return_value=FILE_TOOL_DEFINITIONS), \
                patch("llm.views.handle_file_tool_calls", return_value=FILE_TOOL_RESULTS):
            raw = self._post(enable_file_tools=True, enable_mcp_tools=True)

        assert_stream_is_substantive(
            self, raw, ["file_tool_executed", "tool_call_request", "done"]
        )
        assert_matches_golden(self, "v1_file_and_catalog_tools_in_one_turn", raw)

    # --- (c) provider error mid-stream --------------------------------

    def test_provider_error_mid_stream_transcript(self):
        self.provider.queue(failing_stream(
            [
                generation_id_chunk(GENERATION_ID),
                content_chunk("The notes "),
            ],
            PROVIDER_ERROR_MESSAGE,
        ))

        raw = self._post()

        assert_stream_is_substantive(self, raw, ["content", "error"])
        assert_matches_golden(self, "v1_provider_error_mid_stream", raw)

    # --- Fixtures -----------------------------------------------------

    def _seed_mcp_tool(self):
        from mcp.models import MCPServer, MCPTool

        server = MCPServer.objects.create(
            name="Fixture Search Server",
            description="MCP server backing the golden transcripts.",
            transport_type=MCPServer.TransportType.HTTP,
            url="http://mcp.invalid/search",
        )
        return MCPTool.objects.create(
            server=server,
            name=CATALOG_TOOL_NAME,
            description="Search the web for current information.",
            input_schema={
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        )

    def _patched_mcp_registry(self, tools):
        class FakeRegistry:
            def get_available_tools_sync(self, _user):
                return tools

        return patch("mcp.registry.get_registry", return_value=FakeRegistry())
