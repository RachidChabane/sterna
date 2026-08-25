"""Animate Character tool: schema wraps `llm.tool_catalog.core_tools.ANIMATE_CHARACTER`, execution delegates to the injected legacy invoker."""

from __future__ import annotations

from llm.tool_catalog.core_tools import ANIMATE_CHARACTER as _LEGACY

from ..registry import ToolApproval, ToolDefinition, ToolDisplay
from ._legacy import delegate_to_invoker

PROMPT_SNIPPET = 'Animate characters using a reference performance video (Act Two). Requires a character image/video URL and a reference performance video URL (3-30 seconds).'

TOOL = ToolDefinition(
    id=_LEGACY.id,
    display=ToolDisplay(name=_LEGACY.name),
    description=_LEGACY.description,
    input_schema=_LEGACY.input_schema,
    handler=delegate_to_invoker(_LEGACY.id),
    approval=ToolApproval.REQUIRED,
    prompt_snippet=PROMPT_SNIPPET,
)
