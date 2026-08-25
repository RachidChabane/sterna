"""Generate Image tool: schema wraps `llm.tool_catalog.core_tools.GENERATE_IMAGE`, execution delegates to the injected legacy invoker."""

from __future__ import annotations

from llm.tool_catalog.core_tools import GENERATE_IMAGE as _LEGACY

from ..registry import ToolApproval, ToolDefinition, ToolDisplay
from ._legacy import delegate_to_invoker

# Transcribed from `_LEGACY.system_prompt_section` at wrap time — kept as an
# independent literal so a coverage test can catch drift from the source of
# truth in `llm.tool_catalog.core_tools`, rather than compare a value against
# itself.
PROMPT_SNIPPET = 'Image generation with Nano Banana models. Be specific about style, composition, lighting. Use aspect_ratio 16:9 for landscape, 9:16 for portrait.'

TOOL = ToolDefinition(
    id=_LEGACY.id,
    display=ToolDisplay(name=_LEGACY.name),
    description=_LEGACY.description,
    input_schema=_LEGACY.input_schema,
    handler=delegate_to_invoker(_LEGACY.id),
    approval=ToolApproval.AUTO,
    prompt_snippet=PROMPT_SNIPPET,
)
