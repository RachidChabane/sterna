"""What the V1 streaming endpoint does that no golden transcript shows.

The committed transcripts pin the bytes of five conversations that all
start from a bare user message. Everything a V1 request can carry
beyond that -- the tool exchange a client posts back once the user has
signed off, the sampling parameters, a reasoning trace -- is checked
here against what actually reached the provider port and the database.
"""

import json
from unittest.mock import patch

from rest_framework.test import APIClient, APITestCase

from llm.agent_core.events import Usage
from llm.agent_core.provider import (
    ProviderContentDeltaChunk,
    ProviderDoneChunk,
    ProviderGenerationIdChunk,
    ProviderReasoningDeltaChunk,
    ProviderToolCallDeltaChunk,
    ProviderUsageChunk,
)
from llm.tests.agent_core_doubles import ScriptedProvider
from llm.tests.conftest import make_billing_user, seed_billing_plan
from llm.tests.golden.harness import (
    BILLING_PLAN_NAME,
    CATALOG_TOOL_CALL_ID,
    CATALOG_TOOL_NAME,
    CONVERSATION_ID,
    FILE_TOOL_CALL_ID,
    FILE_TOOL_NAME,
    GENERATION_ID,
    MODEL_ID,
    capture_sse,
    parse_event_names,
    seed_model_catalog,
)

STREAM_URL = "/api/llm/completions/stream-complete/"

STOP = "stop"
TOOL_CALLS = "tool_calls"

TOOL_ROLE = "tool"
ASSISTANT_ROLE = "assistant"

FILE_TOOL_ARGUMENTS = json.dumps({"path": "/workspace/notes.md"})
CATALOG_TOOL_ARGUMENTS = json.dumps({"query": "sterna streaming"})
TOOL_RESULT_CONTENT = json.dumps({"success": True, "content": "# Notes\n"})

APPROVED_EXCHANGE = [
    {"role": "user", "content": "Summarize the notes."},
    {
        "role": ASSISTANT_ROLE,
        "content": "",
        "tool_calls": [
            {
                "id": FILE_TOOL_CALL_ID,
                "type": "function",
                "function": {"name": FILE_TOOL_NAME, "arguments": FILE_TOOL_ARGUMENTS},
            }
        ],
    },
    {
        "role": TOOL_ROLE,
        "tool_call_id": FILE_TOOL_CALL_ID,
        "name": FILE_TOOL_NAME,
        "content": TOOL_RESULT_CONTENT,
    },
]


class NoWaitRateLimiter:
    """Rate limiter stand-in: the real one sleeps against a shared cache."""

    def wait_if_needed(self, *_args, **_kwargs):
        return None


class FixtureSandboxExecutor:
    """Sandbox executor stand-in: answers any call with a fixed result."""

    def __init__(self, **_kwargs):
        pass

    async def invoke(self, _tool_id, _arguments, _context):
        return {"success": True, "content": "# Notes\n"}


class FakeRegistry:
    """MCP registry stand-in listing a fixed set of tools for any user."""

    def __init__(self, tools):
        self._tools = list(tools)

    def get_available_tools_sync(self, _user):
        return list(self._tools)

    async def get_available_tools(self, _user):
        return list(self._tools)


def answering_generation(*fragments, finish_reason=STOP):
    return [
        ProviderGenerationIdChunk(generation_id=GENERATION_ID),
        *(ProviderContentDeltaChunk(content=text) for text in fragments),
        ProviderUsageChunk(
            usage=Usage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
            cost=0.0001,
        ),
        ProviderDoneChunk(finish_reason=finish_reason),
    ]


class V1StreamingEndpointTests(APITestCase):
    """The V1 endpoint's behaviour beyond the bytes its transcripts pin."""

    def setUp(self):
        seed_model_catalog()
        plan = seed_billing_plan(BILLING_PLAN_NAME)
        self.user = make_billing_user("v1-endpoint@example.com", plan)
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.provider = None

    def _post(self, script, *, mcp_tools=(), **overrides):
        payload = {
            "model": MODEL_ID,
            "messages": [{"role": "user", "content": "Summarize the notes."}],
            "conversation_id": CONVERSATION_ID,
        }
        payload.update(overrides)
        self.provider = ScriptedProvider(script)
        with patch("llm.views.completions.RateLimiter", NoWaitRateLimiter), \
                patch(
                    "llm.services.api_key_resolver.resolve_endpoint",
                    return_value=("sk-fixture", None, "platform", None),
                ), \
                patch(
                    "llm.agent_service.dependencies.OpenRouterProvider",
                    return_value=self.provider,
                ), \
                patch(
                    "mcp.registry.get_registry", return_value=FakeRegistry(mcp_tools)
                ):
            return capture_sse(self.client.post(STREAM_URL, payload, format="json"))

    # --- The conversation resumed after an approval ---------------------

    def test_an_approved_tool_exchange_reaches_the_model_intact(self):
        self._post([answering_generation("The notes open with a heading.")],
                   messages=APPROVED_EXCHANGE)

        sent = self.provider.requests[0].messages
        assistant = next(m for m in sent if m.role == ASSISTANT_ROLE)
        result = next(m for m in sent if m.role == TOOL_ROLE)
        self.assertEqual(assistant.tool_calls[0].id, FILE_TOOL_CALL_ID)
        self.assertEqual(assistant.tool_calls[0].function.name, FILE_TOOL_NAME)
        self.assertEqual(assistant.tool_calls[0].function.arguments, FILE_TOOL_ARGUMENTS)
        self.assertEqual(result.tool_call_id, FILE_TOOL_CALL_ID)
        self.assertEqual(result.name, FILE_TOOL_NAME)
        self.assertEqual(result.content, TOOL_RESULT_CONTENT)

    # --- The approval records the frontend answers against --------------

    def test_a_gated_call_opens_the_approval_row_the_stream_names(self):
        from mcp.models import MCPToolApproval

        tool = self._seed_mcp_tool()
        raw = self._post(
            [
                [
                    ProviderGenerationIdChunk(generation_id=GENERATION_ID),
                    ProviderToolCallDeltaChunk(
                        index=0,
                        id=CATALOG_TOOL_CALL_ID,
                        name=CATALOG_TOOL_NAME,
                        arguments_delta=CATALOG_TOOL_ARGUMENTS,
                    ),
                    ProviderUsageChunk(
                        usage=Usage(
                            prompt_tokens=10, completion_tokens=5, total_tokens=15
                        ),
                        cost=0.0001,
                    ),
                    ProviderDoneChunk(finish_reason=TOOL_CALLS),
                ]
            ],
            mcp_tools=[tool],
            enable_mcp_tools=True,
        )

        approval = MCPToolApproval.objects.get(user=self.user, tool=tool)
        self.assertEqual(approval.status, MCPToolApproval.ApprovalStatus.PENDING)
        self.assertEqual(approval.proposed_arguments, {"query": "sterna streaming"})
        announced = _payload_of(raw, "tool_call_request")["approvals"][0]
        self.assertEqual(announced["id"], str(approval.pk))
        self.assertEqual(announced["tool_id"], str(tool.pk))
        self.assertEqual(announced["server_name"], tool.server.name)

    # --- What the request carries upstream ------------------------------

    def test_sampling_parameters_reach_the_provider(self):
        self._post(
            [answering_generation("Done.")],
            temperature=0.2,
            top_p=0.8,
            top_k=40,
            frequency_penalty=0.5,
        )

        request = self.provider.requests[0]
        self.assertEqual(request.temperature, 0.2)
        self.assertEqual(request.extra["top_p"], 0.8)
        self.assertEqual(request.extra["top_k"], 40)
        self.assertEqual(request.extra["frequency_penalty"], 0.5)

    def test_a_turn_takes_at_most_one_recall(self):
        """V1 asks the model again once the tools have run, and no further."""

        tool_calling_generation = [
            ProviderGenerationIdChunk(generation_id=GENERATION_ID),
            ProviderToolCallDeltaChunk(
                index=0,
                id=FILE_TOOL_CALL_ID,
                name=FILE_TOOL_NAME,
                arguments_delta=FILE_TOOL_ARGUMENTS,
            ),
            ProviderUsageChunk(
                usage=Usage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
                cost=0.0001,
            ),
            ProviderDoneChunk(finish_reason=TOOL_CALLS),
        ]
        with patch(
            "llm.agent_service.dependencies.SandboxToolInvoker", FixtureSandboxExecutor
        ):
            self._post([tool_calling_generation], enable_file_tools=True)

        self.assertEqual(self.provider.call_count, 2)

    def test_a_request_without_tools_offers_the_model_none(self):
        self._post([answering_generation("Done.")])

        request = self.provider.requests[0]
        self.assertIsNone(request.tools)
        self.assertIsNone(request.tool_choice)

    def test_a_reasoning_turn_asks_for_a_trace_and_reports_it_on_done(self):
        raw = self._post(
            [
                [
                    ProviderGenerationIdChunk(generation_id=GENERATION_ID),
                    ProviderReasoningDeltaChunk(content="Weighing "),
                    ProviderReasoningDeltaChunk(content="the options."),
                    ProviderContentDeltaChunk(content="Two open items."),
                    ProviderUsageChunk(
                        usage=Usage(
                            prompt_tokens=10, completion_tokens=5, total_tokens=15
                        ),
                        cost=0.0001,
                    ),
                    ProviderDoneChunk(finish_reason=STOP),
                ]
            ],
            enable_reasoning=True,
        )

        self.assertEqual(
            self.provider.requests[0].extra["reasoning"]["exclude"], False
        )
        self.assertNotIn("reasoning", parse_event_names(raw))
        self.assertEqual(
            _payload_of(raw, "done")["reasoning_content"], "Weighing the options."
        )

    # --- Fixtures -------------------------------------------------------

    def _seed_mcp_tool(self):
        from mcp.models import MCPServer, MCPTool

        server = MCPServer.objects.create(
            name="Fixture Search Server",
            description="MCP server backing the endpoint tests.",
            transport_type=MCPServer.TransportType.HTTP,
            url="http://mcp.invalid/search",
        )
        return MCPTool.objects.create(
            server=server,
            name=CATALOG_TOOL_NAME,
            description="Search the web for current information.",
            input_schema={"type": "object", "properties": {"query": {"type": "string"}}},
        )


def _payload_of(raw: bytes, event_name: str) -> dict:
    """The JSON payload of the first frame carrying `event_name`."""

    for frame in raw.decode("utf-8").split("\n\n"):
        if frame.startswith(f"event: {event_name}\n"):
            return json.loads(frame.split("data: ", 1)[1])
    raise AssertionError(f"no {event_name!r} frame in {parse_event_names(raw)}")
