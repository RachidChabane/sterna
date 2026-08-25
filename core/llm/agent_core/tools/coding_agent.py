"""Coding Agent tool: schema wraps `llm.tool_catalog.core_tools.CODING_AGENT`, execution delegates to the injected legacy invoker."""

from __future__ import annotations

from llm.tool_catalog.core_tools import CODING_AGENT as _LEGACY

from ..registry import ToolApproval, ToolDefinition, ToolDisplay
from ._legacy import delegate_to_invoker

PROMPT_SNIPPET = 'Coding Agent for complex multi-step coding tasks. Delegates to an autonomous AI that can explore codebases, write/edit code, run commands, and iterate. Use for tasks requiring multiple operations across files.'

TOOL = ToolDefinition(
    id=_LEGACY.id,
    display=ToolDisplay(name=_LEGACY.name),
    description=_LEGACY.description,
    input_schema=_LEGACY.input_schema,
    handler=delegate_to_invoker(_LEGACY.id),
    approval=ToolApproval.REQUIRED,
    prompt_snippet=PROMPT_SNIPPET,
)
