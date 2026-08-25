"""Golden SSE transcripts for the V1 streaming endpoint.

`CompletionViewSet.stream_complete` runs its turn on the agent core:
the loop streams the model through the provider port, runs the
sandboxed workspace tools a generation asked for, stops on every other
call until the user has signed off, and the V1 wire renders what comes
out as the frames a direct-completion client reads.

Three collaborators are replaced so the transcript depends only on the
loop and the wire: the provider port, by a scripted stand-in replaying
a fixed list of chunks per generation; the sandbox executor, by one
with fixed results; and the cost accountant, by the per-generation
split the fixtures state -- which is the half of the old provider
stand-in that reported what a generation cost.
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
    ProviderToolCallDeltaChunk,
    ProviderUsageChunk,
)
from llm.agent_core.provider_errors import ProviderTransportError
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
from llm.tests.parity.doubles import ReportedCostSplit
from llm.tests.parity.scenarios import (
    V1_FIRST_GENERATION_COST,
    V1_FOLLOW_UP_GENERATION_COST,
)

pytestmark = pytest.mark.golden

STREAM_URL = "/api/llm/completions/stream-complete/"

STOP = "stop"
TOOL_CALLS = "tool_calls"
FIRST_CALL_INDEX = 0
SECOND_CALL_INDEX = 1

FILE_TOOL_ARGUMENTS = json.dumps({"path": "/workspace/notes.md"})
CATALOG_TOOL_ARGUMENTS = json.dumps({"query": "sterna streaming"})

FILE_TOOL_RESULT = {"success": True, "content": "# Notes\nfirst line\n"}


class FixtureSandboxExecutor:
    """Sandbox executor stand-in: answers the fixture tool with a fixed result."""

    def __init__(self, **_kwargs):
        pass

    async def invoke(self, _tool_id, _arguments, _context):
        return dict(FILE_TOOL_RESULT)


class NoWaitRateLimiter:
    """Rate limiter stand-in: the real one sleeps against a shared cache."""

    def wait_if_needed(self, *_args, **_kwargs):
        return None


def generation_id_chunk(generation_id):
    return ProviderGenerationIdChunk(generation_id=generation_id)


def content_chunk(text):
    return ProviderContentDeltaChunk(content=text)


def usage_chunk(prompt_tokens, completion_tokens, cost):
    return ProviderUsageChunk(
        usage=Usage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
        ),
        cost=cost,
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


class V1StreamCompleteGoldenTests(APITestCase):
    """Byte-exact transcripts of `CompletionViewSet.stream_complete`."""

    def setUp(self):
        seed_model_catalog()
        plan = seed_billing_plan(BILLING_PLAN_NAME)
        self.user = make_billing_user("v1-golden@example.com", plan)
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def _post(self, script, *costs, mcp_tools=(), **overrides):
        payload = {
            "model": MODEL_ID,
            "messages": [{"role": "user", "content": "Summarize the notes."}],
            "temperature": 0.2,
            "max_tokens": 256,
            "top_p": 1.0,
            "conversation_id": CONVERSATION_ID,
        }
        payload.update(overrides)

        provider = ScriptedProvider(script)
        patches = [
            patch("llm.views.completions.RateLimiter", NoWaitRateLimiter),
            patch(
                "llm.services.api_key_resolver.resolve_endpoint",
                return_value=("sk-golden-fixture", None, "platform", None),
            ),
            patch(
                "llm.agent_service.dependencies.OpenRouterProvider",
                return_value=provider,
            ),
            patch(
                "llm.agent_service.dependencies.SandboxToolInvoker",
                FixtureSandboxExecutor,
            ),
            patch(
                "llm.agent_service.dependencies.CatalogPriceCostAccountant.for_model",
                return_value=ReportedCostSplit(costs or (V1_FIRST_GENERATION_COST,)),
            ),
            patch("mcp.registry.get_registry", return_value=FakeRegistry(mcp_tools)),
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
        raw = self._post([
            [
                generation_id_chunk(GENERATION_ID),
                content_chunk("The notes "),
                content_chunk("list two "),
                content_chunk("open items."),
                usage_chunk(120, 40, V1_FIRST_GENERATION_COST.total),
                ProviderDoneChunk(finish_reason=STOP),
            ]
        ])

        assert_stream_is_substantive(self, raw, ["generation_id", "content", "done"])
        assert_matches_golden(self, "v1_plain_text_completion", raw)

    # --- (b) tool-call round trips ------------------------------------

    def test_file_tool_round_trip_transcript(self):
        raw = self._post(
            [
                [
                    generation_id_chunk(GENERATION_ID),
                    content_chunk("Reading the file."),
                    file_call_chunk(),
                    usage_chunk(120, 40, V1_FIRST_GENERATION_COST.total),
                    ProviderDoneChunk(finish_reason=TOOL_CALLS),
                ],
                [
                    generation_id_chunk(FOLLOW_UP_GENERATION_ID),
                    content_chunk("The notes "),
                    content_chunk("open with a heading."),
                    usage_chunk(200, 25, V1_FOLLOW_UP_GENERATION_COST.total),
                    ProviderDoneChunk(finish_reason=STOP),
                ],
            ],
            V1_FIRST_GENERATION_COST,
            V1_FOLLOW_UP_GENERATION_COST,
            enable_file_tools=True,
        )

        assert_stream_is_substantive(
            self, raw, ["generation_id", "content", "file_tool_executed", "done"]
        )
        assert_matches_golden(self, "v1_file_tool_round_trip", raw)

    def test_catalog_tool_approval_gate_transcript(self):
        raw = self._post(
            [
                [
                    generation_id_chunk(GENERATION_ID),
                    content_chunk("Searching the web."),
                    catalog_call_chunk(),
                    usage_chunk(120, 40, V1_FIRST_GENERATION_COST.total),
                    ProviderDoneChunk(finish_reason=TOOL_CALLS),
                ]
            ],
            mcp_tools=[self._seed_mcp_tool()],
            enable_mcp_tools=True,
        )

        assert_stream_is_substantive(self, raw, ["tool_call_request", "done"])
        assert_matches_golden(self, "v1_catalog_tool_approval_gate", raw)

    def test_file_and_catalog_tools_in_one_turn_transcript(self):
        raw = self._post(
            [
                [
                    generation_id_chunk(GENERATION_ID),
                    content_chunk("Reading the file and searching the web."),
                    file_call_chunk(FIRST_CALL_INDEX),
                    catalog_call_chunk(SECOND_CALL_INDEX),
                    usage_chunk(120, 40, V1_FIRST_GENERATION_COST.total),
                    ProviderDoneChunk(finish_reason=TOOL_CALLS),
                ]
            ],
            mcp_tools=[self._seed_mcp_tool()],
            enable_file_tools=True,
            enable_mcp_tools=True,
        )

        assert_stream_is_substantive(
            self, raw, ["file_tool_executed", "tool_call_request", "done"]
        )
        assert_matches_golden(self, "v1_file_and_catalog_tools_in_one_turn", raw)

    # --- (c) provider error mid-stream --------------------------------

    def test_provider_error_mid_stream_transcript(self):
        raw = self._post([
            [
                generation_id_chunk(GENERATION_ID),
                content_chunk("The notes "),
                ProviderTransportError(PROVIDER_ERROR_MESSAGE),
            ]
        ])

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


class FakeRegistry:
    """MCP registry stand-in listing a fixed set of tools for any user."""

    def __init__(self, tools):
        self._tools = list(tools)

    def get_available_tools_sync(self, _user):
        return list(self._tools)

    async def get_available_tools(self, _user):
        return list(self._tools)
