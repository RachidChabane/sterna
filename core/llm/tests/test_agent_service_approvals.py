"""`StoredToolApprovals` resolves a gated call's `MCPTool` row correctly
whichever endpoint's naming strategy shaped `ToolDefinition.id`.

V1 offers an MCP tool under the bare name its server publishes; V2
offers the same tool under a server-prefixed id (see
`agent_service.mcp_port`). A lookup keyed on `definition.id` alone
would silently stop matching for one of the two the moment their
naming diverges -- these tests pin that both still resolve to a real,
addressable `MCPToolApproval` row, that two servers with a same-named
tool are not conflated, and that a call naming no known tool still
gets no approval (the one case a caller must not act on).
"""

from __future__ import annotations

import json

from django.test import TestCase

from asgiref.sync import async_to_sync

from authentication.models import User
from llm.agent_core.events import ToolCall, ToolCallFunction
from llm.agent_core.registry import ToolApproval, ToolDefinition, ToolDisplay
from llm.agent_service.approvals import StoredToolApprovals
from llm.agent_service.mcp_port import published_tool_id, server_prefixed_tool_id
from mcp.models import MCPServer, MCPTool, MCPToolApproval


async def _noop_handler(_arguments, _context):
    return {}


def _call(call_id: str, tool_id: str) -> ToolCall:
    return ToolCall(
        id=call_id,
        function=ToolCallFunction(name=tool_id, arguments=json.dumps({"q": "x"})),
    )


def _definition(*, tool_id: str, display_name: str, server_name: str) -> ToolDefinition:
    return ToolDefinition(
        id=tool_id,
        display=ToolDisplay(name=display_name, server_name=server_name),
        description="A tool surfaced through an MCP server.",
        input_schema={"type": "object", "properties": {}},
        handler=_noop_handler,
        approval=ToolApproval.REQUIRED,
    )


class StoredToolApprovalsResolutionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="approvals@t.com", password="x")
        self.server = MCPServer.objects.create(
            user=self.user,
            name="Docs MCP",
            npm_package="@modelcontextprotocol/server-docs",
            transport_type=MCPServer.TransportType.SANDBOXED,
            is_active=True,
        )
        self.tool = MCPTool.objects.create(
            server=self.server,
            name="search_docs",
            description="Search the docs.",
            input_schema={"type": "object", "properties": {}},
        )

    def test_a_v2_style_prefixed_id_still_resolves_the_mcp_tool_row(self):
        prefixed_id = server_prefixed_tool_id(self.server.name, self.tool.name)
        definition = _definition(
            tool_id=prefixed_id,
            display_name=self.tool.name,
            server_name=self.server.name,
        )
        approvals = StoredToolApprovals(user_id=str(self.user.pk))

        opened = async_to_sync(approvals.open)(
            [(_call("call-1", prefixed_id), definition)]
        )

        self.assertEqual(len(opened), 1)
        self.assertEqual(opened[0].tool_id, str(self.tool.pk))
        self.assertTrue(
            MCPToolApproval.objects.filter(pk=opened[0].id, tool=self.tool).exists()
        )

    def test_a_v1_style_bare_id_still_resolves_the_mcp_tool_row(self):
        bare_id = published_tool_id(self.server.name, self.tool.name)
        definition = _definition(
            tool_id=bare_id, display_name=self.tool.name, server_name=self.server.name
        )
        approvals = StoredToolApprovals(user_id=str(self.user.pk))

        opened = async_to_sync(approvals.open)(
            [(_call("call-1", bare_id), definition)]
        )

        self.assertEqual(len(opened), 1)
        self.assertEqual(opened[0].tool_id, str(self.tool.pk))

    def test_two_servers_with_a_same_named_tool_are_not_conflated(self):
        other_server = MCPServer.objects.create(
            user=self.user,
            name="Notes MCP",
            npm_package="@modelcontextprotocol/server-notes",
            transport_type=MCPServer.TransportType.SANDBOXED,
            is_active=True,
        )
        other_tool = MCPTool.objects.create(
            server=other_server,
            name=self.tool.name,
            description="Same name, different server.",
            input_schema={"type": "object", "properties": {}},
        )
        prefixed_id = server_prefixed_tool_id(other_server.name, other_tool.name)
        definition = _definition(
            tool_id=prefixed_id,
            display_name=other_tool.name,
            server_name=other_server.name,
        )
        approvals = StoredToolApprovals(user_id=str(self.user.pk))

        opened = async_to_sync(approvals.open)(
            [(_call("call-1", prefixed_id), definition)]
        )

        self.assertEqual(len(opened), 1)
        self.assertEqual(opened[0].tool_id, str(other_tool.pk))

    def test_a_stale_server_name_still_resolves_by_the_tool_name_alone(self):
        definition = _definition(
            tool_id=server_prefixed_tool_id("Renamed Server", self.tool.name),
            display_name=self.tool.name,
            server_name="Renamed Server",
        )
        approvals = StoredToolApprovals(user_id=str(self.user.pk))

        opened = async_to_sync(approvals.open)(
            [(_call("call-1", "irrelevant"), definition)]
        )

        self.assertEqual(len(opened), 1)
        self.assertEqual(opened[0].tool_id, str(self.tool.pk))

    def test_a_call_naming_no_known_tool_gets_no_approval(self):
        definition = _definition(
            tool_id="mcp_unknown_ghost_tool",
            display_name="ghost_tool",
            server_name="Unknown MCP",
        )
        approvals = StoredToolApprovals(user_id=str(self.user.pk))

        with self.assertLogs("llm.agent_service.approvals", level="WARNING"):
            opened = async_to_sync(approvals.open)(
                [(_call("call-1", "mcp_unknown_ghost_tool"), definition)]
            )

        self.assertEqual(opened, [])
        self.assertEqual(MCPToolApproval.objects.count(), 0)
