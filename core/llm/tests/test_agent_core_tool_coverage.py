"""Coverage test for the tool plugin registry migration.

Diffs the registry's discovered tool ids against the two legacy
sources named in the migration — every `ToolDefinition` module-level
constant in `llm.tool_catalog.core_tools`, and the handler dict
`HTTPToolExecutor.execute_tool_call` dispatches through in
`llm.http_tool_executor` — so a tool present in either legacy source
but missing a registry entry fails loudly rather than silently. This
checks coverage in one direction only: the registry may hold more
tools than these two sources name (an MCP-discovered tool, or one
added directly under `tools/` with no legacy counterpart, is exactly
what the package is for) without failing this test. The catalog side
is read by introspecting the module's namespace rather than trusting
its `CORE_TOOL_DEFINITIONS` list, since that list is itself just one
more place a defined tool can be left out of by mistake. The handler
dict is read by parsing the source rather than importing the module,
since `llm.http_tool_executor` pulls in Django through
`sterna.middleware.request_id` and this test must not require a live
sandbox connection to run.

It also checks each catalog tool's transcribed `prompt_snippet`
against `llm.tool_catalog.core_tools`'s current
`system_prompt_section` for that tool, catching drift between the
literal copied into the tool module and the source of truth it was
copied from.
"""

import unittest

from llm.agent_core.registry import discover_tools
from llm.tests.legacy_tool_sources import (
    catalog_tool_definitions,
    http_tool_executor_handler_ids,
)


class ToolCoverageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.discovered = discover_tools()
        cls.catalog_tools = catalog_tool_definitions()
        cls.catalog_ids = set(cls.catalog_tools)
        cls.http_handler_ids = http_tool_executor_handler_ids()

    def test_every_catalog_tool_has_a_registry_entry(self):
        missing = self.catalog_ids - set(self.discovered)
        self.assertEqual(
            missing, set(), f"catalog tool(s) missing a registry entry: {sorted(missing)}"
        )

    def test_every_http_tool_executor_handler_has_a_registry_entry(self):
        missing = self.http_handler_ids - set(self.discovered)
        self.assertEqual(
            missing, set(), f"http_tool_executor handler(s) missing a registry entry: {sorted(missing)}"
        )

    def test_catalog_tool_prompt_snippets_match_the_legacy_source(self):
        mismatches = []
        for tool_id, legacy_tool in self.catalog_tools.items():
            legacy_snippet = legacy_tool.system_prompt_section
            tool = self.discovered.get(tool_id)
            if tool is None:
                continue
            if tool.prompt_snippet != legacy_snippet:
                mismatches.append((tool_id, tool.prompt_snippet, legacy_snippet))
        self.assertEqual(
            mismatches,
            [],
            "registry prompt_snippet drifted from llm.tool_catalog.core_tools."
            f"system_prompt_section for: {mismatches}",
        )


if __name__ == "__main__":
    unittest.main()
