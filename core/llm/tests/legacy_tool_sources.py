"""Shared readers for the legacy sources `agent_core`'s tests key off.

Three tests each diff `llm.agent_core.tools` against a legacy source of
truth it must not drift from: coverage against every `ToolDefinition`
constant in `llm.tool_catalog.core_tools` and every handler id
`HTTPToolExecutor.execute_tool_call` dispatches
(`test_agent_core_tool_coverage.py`); schema fidelity against
`sandbox.orchestrator.file_tools.FILE_TOOLS`, the model-facing tool
contract legacy V1 sends the model
(`test_agent_core_file_tools_drift.py`); and default approval against
the union of the same two legacy sources
(`test_agent_core_approval_classification.py`). This module reads all
three once so each test imports rather than re-derives them.

`http_tool_executor_handler_ids` and `file_tools_definitions` parse
their source file with `ast` instead of importing it:
`llm.http_tool_executor` pulls in Django through
`sterna.middleware.request_id`, and `sandbox.orchestrator` has no
`__init__.py` — it is not a package the rest of `core` imports from,
and reading it here must not become the first thing that does. Neither
constraint applies to `llm.tool_catalog.core_tools`, which is imported
directly.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any, Dict, List, Set

from llm.tool_catalog import core_tools as core_tools_module
from llm.tool_catalog.models import ToolDefinition as LegacyToolDefinition

CORE_ROOT = Path(__file__).resolve().parent.parent.parent
HTTP_TOOL_EXECUTOR = CORE_ROOT / "llm" / "http_tool_executor.py"
SANDBOX_FILE_TOOLS = CORE_ROOT / "sandbox" / "orchestrator" / "file_tools.py"


def catalog_tool_definitions() -> Dict[str, LegacyToolDefinition]:
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


def http_tool_executor_handler_ids() -> Set[str]:
    """The tool ids `HTTPToolExecutor.execute_tool_call` dispatches, read from source."""

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
