"""Animate Image tool: schema wraps `llm.tool_catalog.core_tools.ANIMATE_IMAGE`, execution delegates to the injected legacy invoker."""

from __future__ import annotations

from llm.tool_catalog.core_tools import ANIMATE_IMAGE as _LEGACY

from ..registry import ToolApproval, ToolDefinition, ToolDisplay
from ._legacy import delegate_to_invoker

PROMPT_SNIPPET = 'Animate static images into videos. Requires an image URL (user-uploaded or public).'

TOOL = ToolDefinition(
    id=_LEGACY.id,
    display=ToolDisplay(name=_LEGACY.name),
    description=_LEGACY.description,
    input_schema=_LEGACY.input_schema,
    handler=delegate_to_invoker(_LEGACY.id),
    approval=ToolApproval.REQUIRED,
    prompt_snippet=PROMPT_SNIPPET,
)
