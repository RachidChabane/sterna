"""Generate Video tool: schema wraps `llm.tool_catalog.core_tools.GENERATE_VIDEO`, execution delegates to the injected legacy invoker."""

from __future__ import annotations

from llm.tool_catalog.core_tools import GENERATE_VIDEO as _LEGACY

from ..registry import ToolApproval, ToolDefinition, ToolDisplay
from ._legacy import delegate_to_invoker

PROMPT_SNIPPET = 'Video generation with OpenAI Sora. Be specific about scene, action, camera movement. Generation takes 1-5 minutes.'

TOOL = ToolDefinition(
    id=_LEGACY.id,
    display=ToolDisplay(name=_LEGACY.name),
    description=_LEGACY.description,
    input_schema=_LEGACY.input_schema,
    handler=delegate_to_invoker(_LEGACY.id),
    approval=ToolApproval.AUTO,
    prompt_snippet=PROMPT_SNIPPET,
)
