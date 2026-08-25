"""Every discovered tool's default `approval` matches V1's classification.

Legacy V1 (`llm.views.stream_complete`) runs a sandbox/file-handler
tool immediately and puts every catalog tool and MCP tool call up for
approval first. `agent_core` encodes that as a per-`ToolDefinition`
`approval` constant, so this test derives the expected AUTO/REQUIRED
partition programmatically from the same two legacy sources
`test_agent_core_tool_coverage.py` diffs the registry against —
`HTTPToolExecutor.execute_tool_call`'s handler dict names the
sandbox/file-handler tools V1 runs immediately, and
`llm.tool_catalog.core_tools`'s constants name the catalog tools V1
gates — and asserts each discovered tool's `approval` matches it,
rather than pinning a second, hand-maintained id list that could drift
from the registry the same way the schemas this migration transcribed
did.

A handler id also present in the catalog (`list_files`, `coding_agent`,
...) is a sandbox/file-handler tool for this purpose: V1 runs it
immediately regardless of whether `core_tools` also happens to
describe it, so handler membership takes precedence over catalog
membership. Every discovered tool is expected to fall in exactly one
of the two sources; the MCP bridge tool is dynamic (minted per server
at runtime, not one of the statically discovered tools) and is not
covered by this partition — its own module pins its approval directly.
"""

from __future__ import annotations

import unittest

from llm.agent_core.registry import ToolApproval, discover_tools
from llm.tests.legacy_tool_sources import (
    catalog_tool_definitions,
    http_tool_executor_handler_ids,
)


class DefaultApprovalMatchesV1ClassificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.discovered = discover_tools()
        cls.handler_ids = http_tool_executor_handler_ids()
        cls.catalog_ids = set(catalog_tool_definitions())

    def test_every_discovered_tool_is_covered_by_exactly_one_legacy_source(self):
        """A tool this migration forgot to classify fails loudly here, not silently.

        A tool in both sources is still covered (handler membership
        takes precedence, per the module docstring); one in neither
        would have no derivable expectation and must not pass by
        omission.
        """

        uncovered = [
            tool_id
            for tool_id in self.discovered
            if tool_id not in self.handler_ids and tool_id not in self.catalog_ids
        ]
        self.assertEqual(
            uncovered,
            [],
            "discovered tool(s) named in neither legacy source, so this test "
            f"cannot derive their expected approval: {sorted(uncovered)}",
        )

    def test_every_discovered_tool_s_approval_matches_the_derived_partition(self):
        mismatches = []
        for tool_id, tool in self.discovered.items():
            expected = (
                ToolApproval.AUTO
                if tool_id in self.handler_ids
                else ToolApproval.REQUIRED
            )
            if tool.approval is not expected:
                mismatches.append((tool_id, tool.approval, expected))
        self.assertEqual(
            mismatches,
            [],
            "approval() drifted from the V1 classification (tool_id, actual, "
            f"expected): {mismatches}",
        )

    def test_a_sandbox_file_handler_tool_that_is_also_cataloged_is_still_auto(self):
        """Pins the precedence rule against a couple of tools a reviewer would
        expect to see explicitly, rather than trusting only the derived loop.
        """

        for tool_id in ("list_files", "coding_agent", "clone_repo"):
            with self.subTest(tool_id=tool_id):
                self.assertIn(tool_id, self.catalog_ids)
                self.assertIn(tool_id, self.handler_ids)
                self.assertIs(self.discovered[tool_id].approval, ToolApproval.AUTO)

    def test_a_catalog_only_tool_is_required(self):
        for tool_id in ("execute_code", "brave_web_search", "query_knowledge_base"):
            with self.subTest(tool_id=tool_id):
                self.assertIn(tool_id, self.catalog_ids)
                self.assertNotIn(tool_id, self.handler_ids)
                self.assertIs(self.discovered[tool_id].approval, ToolApproval.REQUIRED)


if __name__ == "__main__":
    unittest.main()
