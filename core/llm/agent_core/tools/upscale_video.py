"""Upscale Video tool: schema wraps `llm.tool_catalog.core_tools.UPSCALE_VIDEO`, execution delegates to the injected legacy invoker."""

from __future__ import annotations

from llm.tool_catalog.core_tools import UPSCALE_VIDEO as _LEGACY

from ..registry import ToolApproval, ToolDefinition, ToolDisplay
from ._legacy import delegate_to_invoker

PROMPT_SNIPPET = 'Upscale videos to 4x resolution. Requires a video URL.'

TOOL = ToolDefinition(
    id=_LEGACY.id,
    display=ToolDisplay(name=_LEGACY.name),
    description=_LEGACY.description,
    input_schema=_LEGACY.input_schema,
    handler=delegate_to_invoker(_LEGACY.id),
    approval=ToolApproval.REQUIRED,
    prompt_snippet=PROMPT_SNIPPET,
)
