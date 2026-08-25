"""Query Knowledge Base tool: schema wraps `llm.tool_catalog.core_tools.QUERY_KNOWLEDGE_BASE`, execution delegates to the injected legacy invoker."""

from __future__ import annotations

from llm.tool_catalog.core_tools import QUERY_KNOWLEDGE_BASE as _LEGACY

from ..registry import ToolApproval, ToolDefinition, ToolDisplay
from ._legacy import delegate_to_invoker

# Transcribed from `_LEGACY.system_prompt_section` at wrap time — kept as an
# independent literal so a coverage test can catch drift from the source of
# truth in `llm.tool_catalog.core_tools`, rather than compare a value against
# itself.
PROMPT_SNIPPET = "Query the user's personal knowledge base for relevant document excerpts. Cite sources when using retrieved information."

TOOL = ToolDefinition(
    id=_LEGACY.id,
    display=ToolDisplay(name=_LEGACY.name),
    description=_LEGACY.description,
    input_schema=_LEGACY.input_schema,
    handler=delegate_to_invoker(_LEGACY.id),
    approval=ToolApproval.AUTO,
    prompt_snippet=PROMPT_SNIPPET,
)
