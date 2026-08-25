"""Unit tests for `llm.agent_core.registry`: discovery, lookup, and the
handler/context/invoker seam a legacy-backed tool calls through.
"""

import unittest

from llm.agent_core.registry import (
    ToolApproval,
    ToolDefinition,
    ToolDisplay,
    ToolExecutionContext,
    ToolRegistry,
    discover_tools,
)


class _RecordingInvoker:
    """A fake `LegacyToolInvoker` that records what it was called with."""

    def __init__(self, result=None):
        self.calls = []
        self._result = result if result is not None else {"success": True}

    async def invoke(self, tool_id, arguments, context):
        self.calls.append((tool_id, arguments, context))
        return self._result


def _context(invoker) -> ToolExecutionContext:
    return ToolExecutionContext(
        user_id="user-1", conversation_id="conv-1", invoker=invoker, chat_id="chat-1"
    )


class ToolDefinitionTests(unittest.TestCase):
    def test_to_openai_function_shape(self):
        async def handler(arguments, context):
            return {}

        tool = ToolDefinition(
            id="a_tool",
            display=ToolDisplay(name="A Tool"),
            description="Does a thing.",
            input_schema={"type": "object", "properties": {}},
            handler=handler,
            approval=ToolApproval.AUTO,
        )
        self.assertEqual(
            tool.to_openai_function(),
            {
                "type": "function",
                "function": {
                    "name": "a_tool",
                    "description": "Does a thing.",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
        )


class DiscoverToolsTests(unittest.IsolatedAsyncioTestCase):
    def test_discovers_every_public_module_in_the_tools_package(self):
        found = discover_tools()
        self.assertGreater(len(found), 0)
        for tool_id, tool in found.items():
            self.assertIsInstance(tool, ToolDefinition)
            self.assertEqual(tool.id, tool_id)

    def test_skips_underscore_prefixed_helper_modules(self):
        found = discover_tools()
        self.assertNotIn("_legacy", found)

    async def test_a_discovered_tool_s_handler_delegates_to_the_injected_invoker(self):
        found = discover_tools()
        tool = found["read_file"]
        invoker = _RecordingInvoker(result={"success": True, "data": {"content": "hi"}})
        context = _context(invoker)

        result = await tool.handler({"path": "/workspace/a.txt"}, context)

        self.assertEqual(result, {"success": True, "data": {"content": "hi"}})
        self.assertEqual(len(invoker.calls), 1)
        called_id, called_args, called_context = invoker.calls[0]
        self.assertEqual(called_id, "read_file")
        self.assertEqual(called_args, {"path": "/workspace/a.txt"})
        self.assertIs(called_context, context)


class ToolRegistryTests(unittest.TestCase):
    def _tool(self, tool_id: str) -> ToolDefinition:
        async def handler(arguments, context):
            return {}

        return ToolDefinition(
            id=tool_id,
            display=ToolDisplay(name=tool_id),
            description="",
            input_schema={"type": "object", "properties": {}},
            handler=handler,
            approval=ToolApproval.AUTO,
        )

    def test_get_and_all(self):
        registry = ToolRegistry([self._tool("a"), self._tool("b")])
        self.assertEqual(len(registry), 2)
        self.assertIn("a", registry)
        self.assertIsNone(registry.get("missing"))
        self.assertEqual({t.id for t in registry.all()}, {"a", "b"})

    def test_rejects_duplicate_ids(self):
        with self.assertRaises(ValueError):
            ToolRegistry([self._tool("a"), self._tool("a")])

    def test_to_openai_functions_covers_every_tool(self):
        registry = ToolRegistry([self._tool("a"), self._tool("b")])
        names = {f["function"]["name"] for f in registry.to_openai_functions()}
        self.assertEqual(names, {"a", "b"})

    def test_discover_builds_a_registry_from_the_tools_package(self):
        registry = ToolRegistry.discover()
        self.assertIn("list_files", registry)
        self.assertIn("coding_agent", registry)


if __name__ == "__main__":
    unittest.main()
