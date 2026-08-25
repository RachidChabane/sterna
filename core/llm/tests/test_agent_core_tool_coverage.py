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

import ast
import unittest
from pathlib import Path
from typing import Dict, Set

from llm.agent_core.registry import discover_tools
from llm.tool_catalog import core_tools as core_tools_module
from llm.tool_catalog.models import ToolDefinition as LegacyToolDefinition

CORE_ROOT = Path(__file__).resolve().parent.parent.parent
HTTP_TOOL_EXECUTOR = CORE_ROOT / "llm" / "http_tool_executor.py"


def _catalog_tool_definitions() -> Dict[str, LegacyToolDefinition]:
    """Every `ToolDefinition` constant in `core_tools`, by id.

    Reads the module's namespace directly rather than its curated
    `CORE_TOOL_DEFINITIONS` list, which is itself hand-maintained and
    can omit a defined tool without anything catching it.
    """

    return {
        value.id: value
        for value in vars(core_tools_module).values()
        if isinstance(value, LegacyToolDefinition)
    }


def _http_tool_executor_handler_ids() -> Set[str]:
    """The tool ids `HTTPToolExecutor.execute_tool_call` dispatches, read from source."""

    tree = ast.parse(HTTP_TOOL_EXECUTOR.read_text(encoding="utf-8"), filename=str(HTTP_TOOL_EXECUTOR))
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id == "handlers"
            and isinstance(node.value, ast.Dict)
        ):
            return {ast.literal_eval(key) for key in node.value.keys if key is not None}
    raise AssertionError(
        f"could not find a `handlers = {{...}}` dict literal in {HTTP_TOOL_EXECUTOR}; "
        "this test's characterization of the legacy dispatch table is stale."
    )


class ToolCoverageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.discovered = discover_tools()
        cls.catalog_tools = _catalog_tool_definitions()
        cls.catalog_ids = set(cls.catalog_tools)
        cls.http_handler_ids = _http_tool_executor_handler_ids()

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
