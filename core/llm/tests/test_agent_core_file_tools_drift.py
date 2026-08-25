"""Drift guard for the six agent_core tools transcribed from `FILE_TOOLS`.

`llm.agent_core.tools.run_bash`, `.search_code`, `.update_todos`,
`.prepare_pull_request`, `.execute_programming_task`, and
`.explore_codebase` have no entry in `llm.tool_catalog.core_tools`, so
each hand-transcribes its `description` and `input_schema` from the
matching entry of `sandbox.orchestrator.file_tools.FILE_TOOLS` — the
model-facing tool contract legacy V1 sends the model. A hand
transcription can silently drift from its source; this test parses
`FILE_TOOLS` and asserts each of the six still matches it exactly.

The other `FILE_TOOLS` entries with an `agent_core` counterpart
(`list_files`, `read_file`, `write_file`, `edit_file`,
`create_directory`, `delete_file`, `rename_file`) are deliberately not
compared here: their `agent_core` module wraps the corresponding
`llm.tool_catalog.core_tools` constant by reference instead of
transcribing anything, and that catalog schema is the one
`HTTPToolExecutor`'s handler actually honors (`list_files`'s `depth`
argument has no `FILE_TOOLS` counterpart at all). Comparing those
against `FILE_TOOLS` would fail on a real, intentional difference.
Their fidelity to the real source is instead pinned by
`ToolsWrapCoreToolsByReferenceTests` below: an identity check, so a
future edit that replaces the reference with a hand-typed literal
fails immediately rather than only when the two happen to diverge.

`TRANSCRIBED_FROM_FILE_TOOLS` and `WRAPPED_FROM_CORE_TOOLS` are
themselves hand-maintained dicts, so `FileToolsPartitionCoverageTests`
checks them against the discovered registry and `FILE_TOOLS` directly:
every discovered tool overlapping a `FILE_TOOLS` id must land in
exactly one of the two, so a future tool added to either legacy source
without a matching entry here is caught rather than silently
unguarded.
"""

from __future__ import annotations

import unittest

from llm.agent_core.registry import discover_tools
from llm.agent_core.tools import (
    create_directory,
    delete_file,
    edit_file,
    execute_programming_task,
    explore_codebase,
    list_files,
    prepare_pull_request,
    read_file,
    rename_file,
    run_bash,
    search_code,
    update_todos,
    write_file,
)
from llm.tests.legacy_tool_sources import file_tools_definitions
from llm.tool_catalog import core_tools as core_tools_module

# agent_core tool id -> (module, expected FILE_TOOLS entry name)
TRANSCRIBED_FROM_FILE_TOOLS = {
    "run_bash": run_bash,
    "search_code": search_code,
    "update_todos": update_todos,
    "prepare_pull_request": prepare_pull_request,
    "execute_programming_task": execute_programming_task,
    "explore_codebase": explore_codebase,
}

# agent_core tool id -> (module, the core_tools constant it wraps by reference)
WRAPPED_FROM_CORE_TOOLS = {
    "list_files": (list_files, core_tools_module.LIST_FILES),
    "read_file": (read_file, core_tools_module.READ_FILE),
    "write_file": (write_file, core_tools_module.WRITE_FILE),
    "edit_file": (edit_file, core_tools_module.EDIT_FILE),
    "create_directory": (create_directory, core_tools_module.CREATE_DIRECTORY),
    "delete_file": (delete_file, core_tools_module.DELETE_FILE),
    "rename_file": (rename_file, core_tools_module.RENAME_FILE),
}


class TranscribedFromFileToolsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.file_tools = file_tools_definitions()

    def test_every_transcribed_tool_has_a_file_tools_entry(self):
        missing = set(TRANSCRIBED_FROM_FILE_TOOLS) - set(self.file_tools)
        self.assertEqual(
            missing,
            set(),
            f"tool(s) claim to transcribe FILE_TOOLS but no such entry exists: {sorted(missing)}",
        )

    def test_description_matches_file_tools_verbatim(self):
        mismatches = []
        for tool_id, module in TRANSCRIBED_FROM_FILE_TOOLS.items():
            expected = self.file_tools[tool_id]["description"]
            actual = module.TOOL.description
            if actual != expected:
                mismatches.append(tool_id)
        self.assertEqual(
            mismatches,
            [],
            f"description drifted from FILE_TOOLS for: {sorted(mismatches)}",
        )

    def test_input_schema_matches_file_tools_verbatim(self):
        mismatches = []
        for tool_id, module in TRANSCRIBED_FROM_FILE_TOOLS.items():
            expected = self.file_tools[tool_id]["parameters"]
            actual = module.TOOL.input_schema
            if actual != expected:
                mismatches.append(tool_id)
        self.assertEqual(
            mismatches,
            [],
            f"input_schema drifted from FILE_TOOLS for: {sorted(mismatches)}",
        )


class ToolsWrapCoreToolsByReferenceTests(unittest.TestCase):
    """The seven FILE_TOOLS-overlapping tools that wrap `core_tools` instead.

    These pin identity, not equality: an identical-looking hand-typed
    literal would pass an equality check today and silently stop
    tracking the real source the moment `core_tools` changes.
    """

    def test_description_is_the_same_object_as_the_core_tools_constant(self):
        mismatches = []
        for tool_id, (module, legacy) in WRAPPED_FROM_CORE_TOOLS.items():
            if module.TOOL.description is not legacy.description:
                mismatches.append(tool_id)
        self.assertEqual(
            mismatches,
            [],
            f"description is no longer wrapped by reference for: {sorted(mismatches)}",
        )

    def test_input_schema_is_the_same_object_as_the_core_tools_constant(self):
        mismatches = []
        for tool_id, (module, legacy) in WRAPPED_FROM_CORE_TOOLS.items():
            if module.TOOL.input_schema is not legacy.input_schema:
                mismatches.append(tool_id)
        self.assertEqual(
            mismatches,
            [],
            f"input_schema is no longer wrapped by reference for: {sorted(mismatches)}",
        )


class FileToolsPartitionCoverageTests(unittest.TestCase):
    """`TRANSCRIBED_FROM_FILE_TOOLS` and `WRAPPED_FROM_CORE_TOOLS` are themselves
    hand-maintained lists — the exact failure mode the other two test classes
    guard against. This checks them against the sources instead of trusting
    them: every discovered tool that shares an id with a `FILE_TOOLS` entry
    must be in exactly one of the two, so a new hand-transcribed tool added
    without extending `TRANSCRIBED_FROM_FILE_TOOLS`, or a wrapped tool moved
    out of `WRAPPED_FROM_CORE_TOOLS`, fails here rather than passing by
    omission.
    """

    def test_every_file_tools_overlapping_tool_is_in_exactly_one_bucket(self):
        file_tools_ids = set(file_tools_definitions())
        discovered_ids = set(discover_tools())
        overlapping = file_tools_ids & discovered_ids

        uncovered = [
            tool_id
            for tool_id in overlapping
            if tool_id not in TRANSCRIBED_FROM_FILE_TOOLS
            and tool_id not in WRAPPED_FROM_CORE_TOOLS
        ]
        in_both = [
            tool_id
            for tool_id in overlapping
            if tool_id in TRANSCRIBED_FROM_FILE_TOOLS and tool_id in WRAPPED_FROM_CORE_TOOLS
        ]

        self.assertEqual(
            uncovered,
            [],
            "tool(s) overlap a FILE_TOOLS entry but this test does not classify "
            "them as transcribed or wrapped, so their fidelity to the legacy "
            f"source goes unchecked: {sorted(uncovered)}",
        )
        self.assertEqual(
            in_both,
            [],
            f"tool(s) classified as both transcribed and wrapped: {sorted(in_both)}",
        )


if __name__ == "__main__":
    unittest.main()
