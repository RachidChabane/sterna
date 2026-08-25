"""Golden SSE transcripts for the V2 streaming loop.

`stream_complete_langchain` delegates to `LangChainStreamingAgent`, whose
LangChain path accumulates streamed tool-call fragments, runs the tools,
feeds the results back as tool messages, and repeats until the model
answers without calling anything.

The provider is replaced by a fake chat model that replays a fixed list
of chunks per loop iteration, and the tool set by fakes with fixed
results, so the transcript depends only on the loop.
"""

import json
from unittest.mock import AsyncMock, patch

import pytest
from rest_framework.test import APIClient, APITestCase

from llm.agent.tool_registry import AgentToolRegistry
from llm.tests.conftest import (
    FakeChunk,
    FakeStreamingLLM,
    FakeTool,
    make_billing_user,
    seed_billing_plan,
)
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

STREAM_URL = "/api/llm/completions/stream-complete-v2/"

GENERATION_ID_METADATA_KEY = "openrouter_generation_id"

FILE_TOOL_DISPLAY_NAME = "Read File"
CATALOG_TOOL_DISPLAY_NAME = "Web Search"

FILE_TOOL_RESULT = {"success": True, "content": "# Notes\nfirst line\n"}
CATALOG_TOOL_RESULT = {
    "success": True,
    "results": [
        {"url": "https://example.invalid/sterna", "title": "Sterna streaming"},
    ],
}


def fixture_tools():
    """The tool set every V2 golden scenario binds, with fixed results."""
    return [
        FakeTool(
            FILE_TOOL_NAME,
            json.dumps(FILE_TOOL_RESULT),
            description="Read a file from the workspace.",
        ),
        FakeTool(
            CATALOG_TOOL_NAME,
            json.dumps(CATALOG_TOOL_RESULT),
            description="Search the web for current information.",
        ),
    ]


def install_fixture_tools(registry):
    """Replacement for `AgentToolRegistry.load_initial_tools`."""
    registry.tools = fixture_tools()
    registry.display_names.update({
        FILE_TOOL_NAME: FILE_TOOL_DISPLAY_NAME,
        CATALOG_TOOL_NAME: CATALOG_TOOL_DISPLAY_NAME,
    })


class FailingStreamingLLM:
    """Chat model stand-in that fails partway through the first stream."""

    def __init__(self, chunks, message):
        self._chunks = chunks
        self._message = message

    def astream(self, _messages):
        chunks, message = self._chunks, self._message

        async def _generator():
            for chunk in chunks:
                yield chunk
            raise RuntimeError(message)

        return _generator()

    def bind_tools(self, _tools, **_kwargs):
        return self


class NoWaitRateLimiter:
    """Rate limiter stand-in: the real one sleeps against a shared cache."""

    def wait_if_needed(self, *_args, **_kwargs):
        return None


def content_chunk(text, generation_id=None):
    metadata = {GENERATION_ID_METADATA_KEY: generation_id} if generation_id else None
    return FakeChunk(content=text, response_metadata=metadata)


def usage_chunk(prompt_tokens, completion_tokens):
    return FakeChunk(usage_metadata={
        "input_tokens": prompt_tokens,
        "output_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
    })


def tool_call_chunk(call_id, name, arguments, generation_id=None):
    metadata = {GENERATION_ID_METADATA_KEY: generation_id} if generation_id else None
    return FakeChunk(
        tool_call_chunks=[{"index": 0, "id": call_id, "name": name, "args": arguments}],
        response_metadata=metadata,
    )


class V2StreamCompleteLangchainGoldenTests(APITestCase):
    """Byte-exact transcripts of `stream_complete_langchain`."""

    def setUp(self):
        seed_model_catalog()
        plan = seed_billing_plan(BILLING_PLAN_NAME)
        self.user = make_billing_user("v2-golden@example.com", plan)
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def _post(self, chat_model, **overrides):
        payload = {
            "model": MODEL_ID,
            "messages": [{"role": "user", "content": "Summarize the notes."}],
            "temperature": 0.2,
            "max_tokens": 256,
            "conversation_id": CONVERSATION_ID,
        }
        payload.update(overrides)

        patches = [
            patch("llm.views.RateLimiter", NoWaitRateLimiter),
            patch(
                "llm.views.get_user_instructions",
                return_value={"enabled": False, "content": ""},
            ),
            patch(
                "llm.services.api_key_resolver.resolve_endpoint",
                return_value=("sk-golden-fixture", None, "platform", None),
            ),
            patch("llm.langchain_agent.create_chat_model", return_value=chat_model),
            patch("llm.langchain_agent.ENABLE_TOOL_DISCOVERY", False),
            patch("llm.agent.tool_registry.ENABLE_TOOL_DISCOVERY", False),
            patch.object(AgentToolRegistry, "load_initial_tools", install_fixture_tools),
            # The loop pauses after announcing tool calls to leave a cancel
            # window; the wall clock is not part of the transcript.
            patch("llm.agent.streaming.langchain_path.asyncio.sleep", new=AsyncMock()),
        ]
        started = []
        try:
            for active in patches:
                active.start()
                started.append(active)
            response = self.client.post(STREAM_URL, payload, format="json")
            return capture_sse(response)
        finally:
            for active in reversed(started):
                active.stop()

    # --- (a) plain streamed text --------------------------------------

    def test_plain_text_completion_transcript(self):
        chat_model = FakeStreamingLLM([
            content_chunk("The notes ", generation_id=GENERATION_ID),
            content_chunk("list two "),
            content_chunk("open items."),
            usage_chunk(120, 40),
        ])

        raw = self._post(chat_model)

        assert_stream_is_substantive(
            self, raw, ["generation_id", "content", "usage_update", "done"]
        )
        assert_matches_golden(self, "v2_plain_text_completion", raw)

    # --- (b) tool-call round trips ------------------------------------

    def test_file_tool_round_trip_transcript(self):
        chat_model = FakeStreamingLLM(
            [
                content_chunk("Reading the file.", generation_id=GENERATION_ID),
                tool_call_chunk(
                    FILE_TOOL_CALL_ID,
                    FILE_TOOL_NAME,
                    json.dumps({"path": "/workspace/notes.md"}),
                ),
                usage_chunk(120, 40),
            ],
            [
                content_chunk("The notes ", generation_id=FOLLOW_UP_GENERATION_ID),
                content_chunk("open with a heading."),
                usage_chunk(200, 25),
            ],
        )

        raw = self._post(chat_model, enable_file_tools=True)

        assert_stream_is_substantive(
            self,
            raw,
            ["generation_id", "content", "file_tool_executing", "file_tool_executed", "done"],
        )
        assert_matches_golden(self, "v2_file_tool_round_trip", raw)

    def test_catalog_tool_round_trip_transcript(self):
        chat_model = FakeStreamingLLM(
            [
                content_chunk("Searching the web.", generation_id=GENERATION_ID),
                tool_call_chunk(
                    CATALOG_TOOL_CALL_ID,
                    CATALOG_TOOL_NAME,
                    json.dumps({"query": "sterna streaming"}),
                ),
                usage_chunk(120, 40),
            ],
            [
                content_chunk("One result ", generation_id=FOLLOW_UP_GENERATION_ID),
                content_chunk("describes the project."),
                usage_chunk(180, 30),
            ],
        )

        raw = self._post(chat_model, enable_brave_search=True)

        assert_stream_is_substantive(
            self,
            raw,
            ["file_tool_executing", "file_tool_executed", "web_sources", "done"],
        )
        assert_matches_golden(self, "v2_catalog_tool_round_trip", raw)

    def test_file_and_catalog_tools_in_one_turn_transcript(self):
        chat_model = FakeStreamingLLM(
            [
                content_chunk("Reading and searching.", generation_id=GENERATION_ID),
                FakeChunk(tool_call_chunks=[
                    {
                        "index": 0,
                        "id": FILE_TOOL_CALL_ID,
                        "name": FILE_TOOL_NAME,
                        "args": json.dumps({"path": "/workspace/notes.md"}),
                    },
                    {
                        "index": 1,
                        "id": CATALOG_TOOL_CALL_ID,
                        "name": CATALOG_TOOL_NAME,
                        "args": json.dumps({"query": "sterna streaming"}),
                    },
                ]),
                usage_chunk(120, 40),
            ],
            [
                content_chunk("Both sources ", generation_id=FOLLOW_UP_GENERATION_ID),
                content_chunk("agree."),
                usage_chunk(260, 20),
            ],
        )

        raw = self._post(chat_model, enable_file_tools=True, enable_brave_search=True)

        assert_stream_is_substantive(
            self, raw, ["file_tool_executing", "file_tool_executed", "done"]
        )
        assert_matches_golden(self, "v2_file_and_catalog_tools_in_one_turn", raw)

    # --- (c) provider error mid-stream --------------------------------

    def test_provider_error_mid_stream_transcript(self):
        chat_model = FailingStreamingLLM(
            [
                content_chunk("The notes ", generation_id=GENERATION_ID),
                content_chunk("list "),
            ],
            PROVIDER_ERROR_MESSAGE,
        )

        raw = self._post(chat_model)

        assert_stream_is_substantive(self, raw, ["content", "error"])
        assert_matches_golden(self, "v2_provider_error_mid_stream", raw)
