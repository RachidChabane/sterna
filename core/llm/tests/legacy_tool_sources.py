"""Shared readers for the legacy sources `agent_core`'s tests key off.

Three tests each diff `llm.agent_core.tools` against a legacy source of
truth it must not drift from: coverage against every `ToolDefinition`
constant in `llm.tool_catalog.core_tools` and every handler id
`HTTPToolExecutor.execute_tool_call` dispatches
(`test_agent_core_tool_coverage.py` — "which tools exist", not "which
are gated"); schema fidelity against
`sandbox.orchestrator.file_tools.FILE_TOOLS`, the model-facing tool
contract legacy V1 sends the model
(`test_agent_core_file_tools_drift.py`); and default approval against
`V1_AUTO_TOOL_NAMES`, the tool ids the direct-completion endpoint runs
without asking the user first (`test_agent_core_approval_classification.py`
— the real V1 approval gate: everything else that endpoint sees
requires approval, regardless of whether it is also a handler
`HTTPToolExecutor` can dispatch or a catalog tool). This module holds
all four legacy sources so each test imports rather than re-derives
them.

`sandbox_tool_executor_handler_ids` and `file_tools_definitions` parse
their source file with `ast` instead of importing it:
`llm.sandbox_tool_executor` imports Django directly, and
`sandbox.orchestrator` has no `__init__.py` — it is not a package the
rest of `core` imports from, and reading it here must not become the
first thing that does. Neither constraint applies to
`llm.tool_catalog.core_tools`, which is imported directly.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any, Dict, List, Set

from llm.tool_catalog import core_tools as core_tools_module
from llm.tool_catalog.models import ToolDefinition as LegacyToolDefinition

CORE_ROOT = Path(__file__).resolve().parent.parent.parent
HTTP_TOOL_EXECUTOR = CORE_ROOT / "llm" / "sandbox_tool_executor.py"
SANDBOX_FILE_TOOLS = CORE_ROOT / "sandbox" / "orchestrator" / "file_tools.py"

V1_AUTO_TOOL_NAMES: Set[str] = {
    "list_files",
    "read_file",
    "write_file",
    "create_directory",
    "delete_file",
    "rename_file",
}
"""The tool ids the direct-completion endpoint runs without asking first.

Every other call that endpoint sees — a catalog tool, an MCP tool, or
any other sandbox handler — is queued for the user's approval, which is
what makes this set, rather than `HTTPToolExecutor`'s handler dict, V1's
approval classification: a handler id answers "does legacy execution
logic exist for this tool", an orthogonal question from "does this
endpoint run it without asking first".
"""


def catalog_tool_definitions() -> Dict[str, LegacyToolDefinition]:
    """Every `ToolDefinition` constant in `core_tools`, by id.

    Reads the module's namespace directly rather than its curated
    `CORE_TOOL_DEFINITIONS` list, which is itself hand-maintained and
    can omit a defined tool without anything catching it.

    This answers "which tools exist" (V1 offers this to the model via
    the catalog), not "which tools run without approval" — a catalog
    tool is gated same as any other unless it is also named in
    `V1_AUTO_TOOL_NAMES`. Use this only for coverage
    (`test_agent_core_tool_coverage.py`); for the ungated set, read
    `V1_AUTO_TOOL_NAMES` instead.
    """

    return {
        value.id: value
        for value in vars(core_tools_module).values()
        if isinstance(value, LegacyToolDefinition)
    }


def sandbox_tool_executor_handler_ids() -> Set[str]:
    """The tool ids `HTTPToolExecutor.execute_tool_call` dispatches, read from source.

    This answers "which tools exist" (has legacy execution logic
    behind it), not "which tools run without approval" — some handler
    ids gate on approval same as any catalog tool. Use this only for
    coverage (`test_agent_core_tool_coverage.py`); for the ungated set,
    read `views_file_tool_names` instead.
    """

    tree = ast.parse(
        HTTP_TOOL_EXECUTOR.read_text(encoding="utf-8"), filename=str(HTTP_TOOL_EXECUTOR)
    )
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


def file_tools_definitions() -> Dict[str, Dict[str, Any]]:
    """Every entry of `FILE_TOOLS`, by tool name, as its OpenAI-shaped `function` object.

    Each value holds `description` and `parameters` exactly as sent to
    the model, so a caller can compare them directly against an
    `agent_core` `ToolDefinition`'s `description` and `input_schema`.
    """

    tree = ast.parse(
        SANDBOX_FILE_TOOLS.read_text(encoding="utf-8"), filename=str(SANDBOX_FILE_TOOLS)
    )
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == "FILE_TOOLS"
            and node.value is not None
        ):
            tools: List[Dict[str, Any]] = ast.literal_eval(node.value)
            return {entry["function"]["name"]: entry["function"] for entry in tools}
    raise AssertionError(
        f"could not find a `FILE_TOOLS: ... = [...]` literal in {SANDBOX_FILE_TOOLS}; "
        "this test's characterization of the legacy model-facing tool contract is stale."
    )
