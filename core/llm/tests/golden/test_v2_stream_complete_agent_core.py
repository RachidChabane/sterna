"""Golden SSE transcripts for the V2 streaming loop, served by the agent core.

`stream_complete_langchain` routes a turn to `llm.agent_service` when
the request asks for it. The agent loop streams the model through the
provider port, runs whatever tools the generation asked for through the
bound-callable invoker, feeds the results back, and repeats until the
model answers without calling anything.

The provider port is replaced by a scripted stand-in replaying a fixed
list of chunks per generation, and the tool invoker by one with fixed
results, so the transcript depends only on the loop and the wire.
"""

import json
from unittest.mock import patch

import pytest
from rest_framework.test import APIClient, APITestCase

from llm.agent_core.events import Usage
from llm.agent_core.provider import (
    ProviderContentDeltaChunk,
    ProviderDoneChunk,
    ProviderGenerationIdChunk,
    ProviderImageChunk,
    ProviderReasoningDeltaChunk,
    ProviderToolCallDeltaChunk,
    ProviderUsageChunk,
)
from llm.agent_core.provider_errors import ProviderTransportError
from llm.agent_service.flag import HEADER_META_KEY
from llm.tests.agent_core_doubles import ScriptedProvider
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

STREAM_URL = "/api/llm/completions/stream-complete-v2/"
AGENT_CORE_HEADER = HEADER_META_KEY

STOP = "stop"
TOOL_CALLS = "tool_calls"
FIRST_CALL_INDEX = 0
SECOND_CALL_INDEX = 1

FILE_TOOL_ARGUMENTS = json.dumps({"path": "/workspace/notes.md"})
CATALOG_TOOL_ARGUMENTS = json.dumps({"query": "sterna streaming"})

FILE_TOOL_RESULT = {"success": True, "content": "# Notes\nfirst line\n"}
CATALOG_TOOL_RESULT = {
    "success": True,
    "results": [
        {"url": "https://example.invalid/sterna", "title": "Sterna streaming"},
    ],
}

FIXTURE_RESULTS = {
    FILE_TOOL_NAME: FILE_TOOL_RESULT,
    CATALOG_TOOL_NAME: CATALOG_TOOL_RESULT,
}


class FixtureToolInvoker:
    """Tool invoker stand-in: answers each fixture tool with a fixed result."""

    def __init__(self, _bound_callables):
        pass

    async def invoke(self, tool_id, arguments, context):
        return dict(FIXTURE_RESULTS[tool_id])


def generation_id_chunk(generation_id):
    return ProviderGenerationIdChunk(generation_id=generation_id)


def content_chunk(text):
    return ProviderContentDeltaChunk(content=text)


def reasoning_chunk(text):
    return ProviderReasoningDeltaChunk(content=text)


def image_chunk(image_url):
    return ProviderImageChunk(image=image_url)


def usage_chunk(prompt_tokens, completion_tokens):
    return ProviderUsageChunk(
        usage=Usage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
        )
    )


def tool_call_chunk(index, call_id, name, arguments):
    return ProviderToolCallDeltaChunk(
        index=index, id=call_id, name=name, arguments_delta=arguments
    )


def file_call_chunk(index=FIRST_CALL_INDEX):
    return tool_call_chunk(index, FILE_TOOL_CALL_ID, FILE_TOOL_NAME, FILE_TOOL_ARGUMENTS)


def catalog_call_chunk(index=FIRST_CALL_INDEX):
    return tool_call_chunk(
        index, CATALOG_TOOL_CALL_ID, CATALOG_TOOL_NAME, CATALOG_TOOL_ARGUMENTS
    )


class V2StreamCompleteAgentCoreGoldenTests(APITestCase):
    """Byte-exact transcripts of the V2 endpoint served by the agent core."""

    def setUp(self):
        seed_model_catalog()
        plan = seed_billing_plan(BILLING_PLAN_NAME)
        self.user = make_billing_user("v2-agent-core-golden@example.com", plan)
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def _post(self, script, **overrides):
        payload = {
            "model": MODEL_ID,
            "messages": [{"role": "user", "content": "Summarize the notes."}],
            "temperature": 0.2,
            "max_tokens": 256,
            "conversation_id": CONVERSATION_ID,
        }
        payload.update(overrides)

        provider = ScriptedProvider(script)
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
            patch(
                "llm.agent_service.dependencies.OpenRouterProvider",
                return_value=provider,
            ),
            patch(
                "llm.agent_service.dependencies.BoundToolInvoker", FixtureToolInvoker
            ),
        ]
        started = []
        try:
            for active in patches:
                active.start()
                started.append(active)
            response = self.client.post(
                STREAM_URL, payload, format="json", **{AGENT_CORE_HEADER: "on"}
            )
            return capture_sse(response)
        finally:
            for active in reversed(started):
                active.stop()

    # --- (a) plain streamed text --------------------------------------

    def test_plain_text_completion_transcript(self):
        raw = self._post([
            [
                generation_id_chunk(GENERATION_ID),
                content_chunk("The notes "),
                content_chunk("list two "),
                content_chunk("open items."),
                usage_chunk(120, 40),
                ProviderDoneChunk(finish_reason=STOP),
            ]
        ])

        assert_stream_is_substantive(
            self, raw, ["generation_id", "content", "usage_update", "done"]
        )
        assert_matches_golden(self, "v2_plain_text_completion", raw)

    # --- (b) tool-call round trips ------------------------------------

    def test_file_tool_round_trip_transcript(self):
        raw = self._post(
            [
                [
                    generation_id_chunk(GENERATION_ID),
                    content_chunk("Reading the file."),
                    file_call_chunk(),
                    usage_chunk(120, 40),
                    ProviderDoneChunk(finish_reason=TOOL_CALLS),
                ],
                [
                    generation_id_chunk(FOLLOW_UP_GENERATION_ID),
                    content_chunk("The notes "),
                    content_chunk("open with a heading."),
                    usage_chunk(200, 25),
                    ProviderDoneChunk(finish_reason=STOP),
                ],
            ],
            enable_file_tools=True,
        )

        assert_stream_is_substantive(
            self,
            raw,
            ["generation_id", "content", "file_tool_executing", "file_tool_executed", "done"],
        )
        assert_matches_golden(self, "v2_file_tool_round_trip", raw)

    def test_catalog_tool_round_trip_transcript(self):
        raw = self._post(
            [
                [
                    generation_id_chunk(GENERATION_ID),
                    content_chunk("Searching the web."),
                    catalog_call_chunk(),
                    usage_chunk(120, 40),
                    ProviderDoneChunk(finish_reason=TOOL_CALLS),
                ],
                [
                    generation_id_chunk(FOLLOW_UP_GENERATION_ID),
                    content_chunk("One result "),
                    content_chunk("describes the project."),
                    usage_chunk(180, 30),
                    ProviderDoneChunk(finish_reason=STOP),
                ],
            ],
            enable_brave_search=True,
        )

        assert_stream_is_substantive(
            self,
            raw,
            ["file_tool_executing", "file_tool_executed", "web_sources", "done"],
        )
        assert_matches_golden(self, "v2_catalog_tool_round_trip", raw)

    def test_file_and_catalog_tools_in_one_turn_transcript(self):
        raw = self._post(
            [
                [
                    generation_id_chunk(GENERATION_ID),
                    content_chunk("Reading and searching."),
                    file_call_chunk(FIRST_CALL_INDEX),
                    catalog_call_chunk(SECOND_CALL_INDEX),
                    usage_chunk(120, 40),
                    ProviderDoneChunk(finish_reason=TOOL_CALLS),
                ],
                [
                    generation_id_chunk(FOLLOW_UP_GENERATION_ID),
                    content_chunk("Both sources "),
                    content_chunk("agree."),
                    usage_chunk(260, 20),
                    ProviderDoneChunk(finish_reason=STOP),
                ],
            ],
            enable_file_tools=True,
            enable_brave_search=True,
        )

        assert_stream_is_substantive(
            self, raw, ["file_tool_executing", "file_tool_executed", "done"]
        )
        assert_matches_golden(self, "v2_file_and_catalog_tools_in_one_turn", raw)

    # --- (c) provider error mid-stream --------------------------------

    def test_provider_error_mid_stream_transcript(self):
        raw = self._post([
            [
                generation_id_chunk(GENERATION_ID),
                content_chunk("The notes "),
                content_chunk("list "),
                ProviderTransportError(PROVIDER_ERROR_MESSAGE),
            ]
        ])

        assert_stream_is_substantive(self, raw, ["content", "error"])
        assert_matches_golden(self, "v2_provider_error_mid_stream", raw)

    # --- (d) native reasoning / image output ---------------------------

    def test_reasoning_turn_transcript(self):
        raw = self._post(
            [
                [
                    generation_id_chunk(GENERATION_ID),
                    reasoning_chunk("The notes mention two open items."),
                    content_chunk("There are two open items."),
                    usage_chunk(120, 40),
                    ProviderDoneChunk(finish_reason=STOP),
                ]
            ],
            enable_reasoning=True,
        )

        assert_stream_is_substantive(
            self, raw, ["generation_id", "reasoning", "content", "done"]
        )
        assert_matches_golden(self, "v2_reasoning_turn", raw)

    def test_image_output_turn_transcript(self):
        seed_model_catalog(["text", "image"])

        raw = self._post([
            [
                generation_id_chunk(GENERATION_ID),
                content_chunk("Here is the requested image."),
                image_chunk("https://example.invalid/golden-fixture.png"),
                usage_chunk(120, 40),
                ProviderDoneChunk(finish_reason=STOP),
            ]
        ])

        assert_stream_is_substantive(
            self, raw, ["generation_id", "content", "image", "done"]
        )
        assert_matches_golden(self, "v2_image_output_turn", raw)


class NoWaitRateLimiter:
    """Rate limiter stand-in: the real one sleeps against a shared cache."""

    def wait_if_needed(self, *_args, **_kwargs):
        return None
