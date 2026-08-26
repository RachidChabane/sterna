"""Every discovered tool's default `approval` matches V1's real gate.

The direct-completion endpoint runs a call naming one of six tool ids
immediately; every other tool call it sees — catalog tool, MCP tool,
or any other sandbox handler — is queued for the user's approval
first. `V1_AUTO_TOOL_NAMES` is those six, and it, not
`HTTPToolExecutor`'s handler dict, is V1's approval classification: a
handler id answers "does legacy execution logic exist for this tool",
which is an orthogonal question from "does this endpoint run it
without asking first" (`run_bash`, `search_code`, and several others
are dispatchable handlers that V1 still gates).

`agent_core` encodes the six-name partition as a per-`ToolDefinition`
`approval` constant, and the endpoint reads that constant rather than
naming any tool itself, so this test derives the expected
AUTO/REQUIRED split from the six names programmatically. Two live
sources tie them down: every name must be one the endpoint actually
offers, and the registry the endpoint builds must classify exactly
those six as automatic.

The MCP bridge tool is dynamic (minted per server at runtime, not one
of the statically discovered tools under `agent_core.tools`) and is
not covered by this partition; its own module (`mcp_bridge.py`) pins
its approval to `REQUIRED` directly, matching V1, which never
auto-executes a third-party MCP call.
"""

from __future__ import annotations

import asyncio
import unittest

from llm.agent.feature_flags import AgentFeatureFlags
from llm.agent_core.registry import ToolApproval, discover_tools
from llm.agent_service.v1_tools import build_v1_tool_registry, file_tool_ids
from llm.tests.legacy_tool_sources import V1_AUTO_TOOL_NAMES


class DefaultApprovalMatchesV1ClassificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.discovered = discover_tools()
        cls.auto_tool_names = V1_AUTO_TOOL_NAMES

    def test_every_ungated_tool_is_one_the_endpoint_offers(self):
        self.assertTrue(
            self.auto_tool_names <= set(file_tool_ids()),
            "a tool the endpoint runs without asking must be one it offers",
        )

    def test_the_endpoint_s_registry_runs_exactly_those_six_without_asking(self):
        registry = asyncio.run(
            build_v1_tool_registry(
                AgentFeatureFlags(file_tools=True), user_id="0", mcp_tools=None
            )
        )
        automatic = {
            definition.id
            for definition in registry.all()
            if definition.approval is ToolApproval.AUTO
        }
        self.assertEqual(automatic, self.auto_tool_names)

    def test_every_discovered_tool_s_approval_matches_the_derived_partition(self):
        mismatches = []
        for tool_id, tool in self.discovered.items():
            expected = (
                ToolApproval.AUTO
                if tool_id in self.auto_tool_names
                else ToolApproval.REQUIRED
            )
            if tool.approval is not expected:
                mismatches.append((tool_id, tool.approval, expected))
        self.assertEqual(
            mismatches,
            [],
            "approval() drifted from V1's stream_complete gate (tool_id, actual, "
            f"expected): {mismatches}",
        )

    def test_a_gated_tool_name_is_auto_regardless_of_source(self):
        for tool_id in ("list_files", "read_file", "write_file"):
            with self.subTest(tool_id=tool_id):
                self.assertIn(tool_id, self.auto_tool_names)
                self.assertIs(self.discovered[tool_id].approval, ToolApproval.AUTO)

    def test_a_dispatchable_handler_outside_the_gate_is_still_required(self):
        """A tool with legacy execution logic behind it is not automatically ungated.

        `run_bash`, `search_code`, `update_todos`, `prepare_pull_request`,
        `execute_programming_task`, and `explore_codebase` all dispatch
        through legacy code the same way the six gated tools do, but
        none of them is named in `file_tool_names`, so V1 still queues
        them for approval.
        """

        for tool_id in (
            "run_bash",
            "search_code",
            "update_todos",
            "prepare_pull_request",
            "execute_programming_task",
            "explore_codebase",
        ):
            with self.subTest(tool_id=tool_id):
                self.assertNotIn(tool_id, self.auto_tool_names)
                self.assertIs(self.discovered[tool_id].approval, ToolApproval.REQUIRED)

    def test_a_catalog_only_tool_is_required(self):
        for tool_id in ("execute_code", "brave_web_search", "query_knowledge_base"):
            with self.subTest(tool_id=tool_id):
                self.assertNotIn(tool_id, self.auto_tool_names)
                self.assertIs(self.discovered[tool_id].approval, ToolApproval.REQUIRED)

    def test_the_tool_discovery_meta_tools_are_required(self):
        """`search_available_tools` / `get_tool_details` are not in the six-name
        gate either: V2's auto-all approval policy still runs them ungated,
        but their default classification (like every other tool here) is
        `REQUIRED`, matching every tool outside the six file_tool_ids."""

        for tool_id in ("search_available_tools", "get_tool_details"):
            with self.subTest(tool_id=tool_id):
                self.assertNotIn(tool_id, self.auto_tool_names)
                self.assertIs(self.discovered[tool_id].approval, ToolApproval.REQUIRED)

    def test_agent_orchestration_tools_are_required(self):
        """Multi-step / delegating tools are not part of the six-name gate either."""

        for tool_id in (
            "clone_repo",
            "coding_agent",
            "edit_file",
            "edit_plan",
            "plan_implementation",
            "implement_plan",
        ):
            with self.subTest(tool_id=tool_id):
                self.assertNotIn(tool_id, self.auto_tool_names)
                self.assertIs(self.discovered[tool_id].approval, ToolApproval.REQUIRED)


if __name__ == "__main__":
    unittest.main()
