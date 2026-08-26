"""`build_tool_set`'s gate on the two tool-discovery meta-tools.

`search_available_tools` / `get_tool_details` are bound only under the
same condition legacy main required before it built a discovery context
at all: `AgentFeatureFlags.has_tool_features` plus a real `user_id` and
`conversation_id` (see `registry_factory.py`'s module docstring for the
legacy call site). This exercises that gate against the real
`llm.tool_discovery` service — not a double — including one full round
trip through `BoundToolInvoker`, the same invoker `build_turn_stack`
wires tool calls through in production, to catch a wiring break the
schema-only drift guard (`test_agent_core_tool_discovery_drift.py`)
cannot see.
"""

from __future__ import annotations

import asyncio
import unittest

from llm.agent.feature_flags import AgentFeatureFlags
from llm.agent_service.registry_factory import build_tool_set
from llm.agent_service.tool_invoker import BoundToolInvoker

DISCOVERY_TOOL_IDS = {"search_available_tools", "get_tool_details"}


def _run(coro):
    return asyncio.run(coro)


class DiscoveryToolGateTests(unittest.TestCase):
    def test_bound_when_a_tool_feature_and_ids_are_present(self):
        tool_set = _run(
            build_tool_set(
                AgentFeatureFlags(brave_search=True),
                user_id="user-1",
                conversation_id="conv-1",
            )
        )
        self.assertTrue(DISCOVERY_TOOL_IDS <= set(tool_set.bound_callables))
        self.assertTrue(DISCOVERY_TOOL_IDS <= {d.id for d in tool_set.registry.all()})

    def test_not_bound_when_no_tool_feature_is_enabled(self):
        tool_set = _run(
            build_tool_set(
                AgentFeatureFlags(reasoning=True),
                user_id="user-1",
                conversation_id="conv-1",
            )
        )
        self.assertFalse(DISCOVERY_TOOL_IDS & set(tool_set.bound_callables))
        self.assertFalse(DISCOVERY_TOOL_IDS & {d.id for d in tool_set.registry.all()})

    def test_not_bound_with_no_flags_at_all(self):
        tool_set = _run(
            build_tool_set(
                AgentFeatureFlags(),
                user_id="user-1",
                conversation_id="conv-1",
            )
        )
        self.assertFalse(DISCOVERY_TOOL_IDS & set(tool_set.bound_callables))

    def test_not_bound_without_a_user_id(self):
        tool_set = _run(
            build_tool_set(
                AgentFeatureFlags(brave_search=True),
                user_id="",
                conversation_id="conv-1",
            )
        )
        self.assertFalse(DISCOVERY_TOOL_IDS & set(tool_set.bound_callables))

    def test_not_bound_without_a_conversation_id(self):
        tool_set = _run(
            build_tool_set(
                AgentFeatureFlags(brave_search=True),
                user_id="user-1",
                conversation_id="",
            )
        )
        self.assertFalse(DISCOVERY_TOOL_IDS & set(tool_set.bound_callables))


class DiscoveryToolInvocationTests(unittest.TestCase):
    """A full round trip through the real invoker, not just schema matching."""

    def test_search_available_tools_runs_through_the_bound_invoker(self):
        tool_set = _run(
            build_tool_set(
                AgentFeatureFlags(file_tools=True),
                user_id="user-search",
                conversation_id="conv-search",
            )
        )
        invoker = BoundToolInvoker(tool_set.bound_callables)
        context = tool_set.registry.get("search_available_tools")
        self.assertIsNotNone(context)

        from llm.agent_core.registry import ToolExecutionContext

        result = _run(
            invoker.invoke(
                "search_available_tools",
                {"query": "read a file"},
                ToolExecutionContext(
                    user_id="user-search",
                    conversation_id="conv-search",
                    invoker=invoker,
                ),
            )
        )
        self.assertNotIn("error", result)

    def test_get_tool_details_runs_through_the_bound_invoker(self):
        tool_set = _run(
            build_tool_set(
                AgentFeatureFlags(file_tools=True),
                user_id="user-details",
                conversation_id="conv-details",
            )
        )
        invoker = BoundToolInvoker(tool_set.bound_callables)

        from llm.agent_core.registry import ToolExecutionContext

        result = _run(
            invoker.invoke(
                "get_tool_details",
                {"function_name": "read_file"},
                ToolExecutionContext(
                    user_id="user-details",
                    conversation_id="conv-details",
                    invoker=invoker,
                ),
            )
        )
        self.assertNotIn("error", result)


if __name__ == "__main__":
    unittest.main()
