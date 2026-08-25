"""Unit tests for `llm.agent_core.mcp_bridge`: converting a `MCPToolPort`'s
tools into `ToolDefinition`s that always require approval.
"""

import dataclasses
import unittest

from llm.agent_core.mcp_bridge import MCPToolSource, MCPToolSpec
from llm.agent_core.registry import ToolApproval, ToolExecutionContext


class _FakeMCPPort:
    def __init__(self, specs, call_result=None):
        self._specs = specs
        self._call_result = call_result if call_result is not None else {"success": True}
        self.calls = []

    async def list_tools(self, user_id):
        self.list_tools_called_with = user_id
        return self._specs

    async def call_tool(self, user_id, tool_id, arguments):
        self.calls.append((user_id, tool_id, arguments))
        return self._call_result


_DEFAULT_SPEC = MCPToolSpec(
    tool_id="server-1.search",
    server_id="server-1",
    server_name="Notion",
    name="Search",
    description="Search Notion pages.",
    input_schema={"type": "object", "properties": {"query": {"type": "string"}}},
    server_icon_url="https://example.test/icon.png",
    server_icon_invert=True,
)


def _spec(**overrides) -> MCPToolSpec:
    return dataclasses.replace(_DEFAULT_SPEC, **overrides)


class MCPToolSourceTests(unittest.IsolatedAsyncioTestCase):
    async def test_discover_converts_every_spec_to_a_tool_definition(self):
        port = _FakeMCPPort([_spec(), _spec(tool_id="server-1.create", name="Create")])
        source = MCPToolSource(port)

        tools = await source.discover("user-1")

        self.assertEqual(port.list_tools_called_with, "user-1")
        self.assertEqual({t.id for t in tools}, {"server-1.search", "server-1.create"})

    async def test_converted_tool_carries_server_display_metadata(self):
        source = MCPToolSource(_FakeMCPPort([_spec()]))
        [tool] = await source.discover("user-1")

        self.assertEqual(tool.display.name, "Search")
        self.assertEqual(tool.display.server_name, "Notion")
        self.assertEqual(tool.display.icon_url, "https://example.test/icon.png")
        self.assertTrue(tool.display.icon_invert)
        self.assertEqual(tool.description, "Search Notion pages.")
        self.assertEqual(
            tool.input_schema, {"type": "object", "properties": {"query": {"type": "string"}}}
        )

    async def test_converted_tool_always_requires_approval(self):
        source = MCPToolSource(_FakeMCPPort([_spec()]))
        [tool] = await source.discover("user-1")

        self.assertEqual(tool.approval, ToolApproval.REQUIRED)

    async def test_converted_tool_s_handler_calls_back_through_the_port(self):
        port = _FakeMCPPort([_spec()], call_result={"success": True, "data": {"hits": []}})
        source = MCPToolSource(port)
        [tool] = await source.discover("user-1")
        context = ToolExecutionContext(
            user_id="user-1", conversation_id="conv-1", invoker=None
        )

        result = await tool.handler({"query": "roadmap"}, context)

        self.assertEqual(result, {"success": True, "data": {"hits": []}})
        self.assertEqual(port.calls, [("user-1", "server-1.search", {"query": "roadmap"})])


if __name__ == "__main__":
    unittest.main()
