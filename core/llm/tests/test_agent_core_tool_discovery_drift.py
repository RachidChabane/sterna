"""Drift guard for the two agent_core tools transcribed from
`llm.tool_discovery.tool_search`.

`llm.agent_core.tools.search_available_tools` and `.get_tool_details`
have no entry in `llm.tool_catalog.core_tools`, so each hand-transcribes
its `id`, `display.name`, `description`, and `input_schema` from the
matching `ToolDefinition` constant in `llm.tool_discovery.tool_search`
(`TOOL_SEARCH_DEFINITION`, `GET_TOOL_DETAILS_DEFINITION`) instead of
importing it directly — that module imports `langchain_core.tools` at
module scope, which `test_agent_core_tool_import_purity.py` forbids
anywhere in `agent_core`'s transitive import closure. A hand
transcription can silently drift from its source; this test imports
`llm.tool_discovery.tool_search` (a test file is not part of that
purity scan) and asserts both agent_core modules still match it
exactly.
"""

from __future__ import annotations

import unittest

from llm.agent_core.tools import get_tool_details, search_available_tools
from llm.tool_discovery.tool_search import (
    GET_TOOL_DETAILS_DEFINITION,
    TOOL_SEARCH_DEFINITION,
)

# agent_core tool module -> the tool_discovery.tool_search ToolDefinition it transcribes
TRANSCRIBED_FROM_TOOL_DISCOVERY = {
    "search_available_tools": (search_available_tools, TOOL_SEARCH_DEFINITION),
    "get_tool_details": (get_tool_details, GET_TOOL_DETAILS_DEFINITION),
}


class TranscribedFromToolDiscoveryTests(unittest.TestCase):
    def test_id_matches_the_legacy_definition(self):
        mismatches = []
        for tool_id, (module, legacy) in TRANSCRIBED_FROM_TOOL_DISCOVERY.items():
            if module.TOOL.id != legacy.id:
                mismatches.append(tool_id)
        self.assertEqual(mismatches, [], f"id drifted from tool_discovery for: {sorted(mismatches)}")

    def test_display_name_matches_the_legacy_definition(self):
        mismatches = []
        for tool_id, (module, legacy) in TRANSCRIBED_FROM_TOOL_DISCOVERY.items():
            if module.TOOL.display.name != legacy.name:
                mismatches.append(tool_id)
        self.assertEqual(
            mismatches, [], f"display name drifted from tool_discovery for: {sorted(mismatches)}"
        )

    def test_description_matches_the_legacy_definition_verbatim(self):
        mismatches = []
        for tool_id, (module, legacy) in TRANSCRIBED_FROM_TOOL_DISCOVERY.items():
            if module.TOOL.description != legacy.description:
                mismatches.append(tool_id)
        self.assertEqual(
            mismatches, [], f"description drifted from tool_discovery for: {sorted(mismatches)}"
        )

    def test_input_schema_matches_the_legacy_definition_verbatim(self):
        mismatches = []
        for tool_id, (module, legacy) in TRANSCRIBED_FROM_TOOL_DISCOVERY.items():
            if module.TOOL.input_schema != legacy.input_schema:
                mismatches.append(tool_id)
        self.assertEqual(
            mismatches, [], f"input_schema drifted from tool_discovery for: {sorted(mismatches)}"
        )


if __name__ == "__main__":
    unittest.main()
