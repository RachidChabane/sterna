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
the `file_tool_names` set `llm.views.stream_complete` runs ungated
(`test_agent_core_approval_classification.py` — the real V1 approval
gate: everything else that endpoint sees requires approval, regardless
of whether it is also a handler `HTTPToolExecutor` can dispatch or a
catalog tool). This module reads all four legacy sources once so each
test imports rather than re-derives them.

`http_tool_executor_handler_ids`, `file_tools_definitions`, and
`views_file_tool_names` parse their source file with `ast` instead of
importing it: `llm.http_tool_executor` and `llm.views` both import
Django and Django REST Framework directly, and `sandbox.orchestrator`
has no `__init__.py` — it is not a package the rest of `core` imports
from, and reading it here must not become the first thing that does.
Neither constraint applies to `llm.tool_catalog.core_tools`, which is
imported directly.
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
VIEWS = CORE_ROOT / "llm" / "views.py"
STREAM_COMPLETE_FUNCTION_NAME = "stream_complete"
FILE_TOOL_NAMES_VARIABLE_NAME = "file_tool_names"


def catalog_tool_definitions() -> Dict[str, LegacyToolDefinition]:
    """Every `ToolDefinition` constant in `core_tools`, by id.

    Reads the module's namespace directly rather than its curated
    `CORE_TOOL_DEFINITIONS` list, which is itself hand-maintained and
    can omit a defined tool without anything catching it.

    This answers "which tools exist" (V1 offers this to the model via
    the catalog), not "which tools run without approval" — a catalog
    tool is gated same as any other unless it is also named in
    `views_file_tool_names`. Use this only for coverage
    (`test_agent_core_tool_coverage.py`); for the ungated set, read
    `views_file_tool_names` instead.
    """

    return {
        value.id: value
        for value in vars(core_tools_module).values()
        if isinstance(value, LegacyToolDefinition)
    }


def http_tool_executor_handler_ids() -> Set[str]:
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


def views_file_tool_names() -> Set[str]:
    """The tool ids `llm.views.stream_complete` runs without approval, read from source.

    `stream_complete` assigns a `file_tool_names` set literal, then
    later in the same function branches on membership in it: a call
    naming one of these runs immediately, and every other tool call
    from that endpoint — catalog or sandbox alike, `HTTPToolExecutor`
    handler or not — is queued for the user's approval first. This is
    V1's actual approval gate, distinct from
    `http_tool_executor_handler_ids`, which only answers which tools
    have a handler at all.

    Reads by parsing `llm.views` with `ast` rather than importing it:
    `llm.views` imports Django and Django REST Framework directly.
    """

    tree = ast.parse(VIEWS.read_text(encoding="utf-8"), filename=str(VIEWS))
    for node in ast.walk(tree):
        if (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == STREAM_COMPLETE_FUNCTION_NAME
        ):
            for inner in ast.walk(node):
                if (
                    isinstance(inner, ast.Assign)
                    and len(inner.targets) == 1
                    and isinstance(inner.targets[0], ast.Name)
                    and inner.targets[0].id == FILE_TOOL_NAMES_VARIABLE_NAME
                    and isinstance(inner.value, ast.Set)
                ):
                    return set(ast.literal_eval(inner.value))
            raise AssertionError(
                f"could not find a `{FILE_TOOL_NAMES_VARIABLE_NAME} = {{...}}` set "
                f"literal inside `{STREAM_COMPLETE_FUNCTION_NAME}` in {VIEWS}; "
                "this test's characterization of V1's approval gate is stale."
            )
    raise AssertionError(
        f"could not find a `def {STREAM_COMPLETE_FUNCTION_NAME}(...)` function in {VIEWS}; "
        "this test's characterization of V1's approval gate is stale."
    )
