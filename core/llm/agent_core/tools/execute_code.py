"""Execute Code tool: schema wraps `llm.tool_catalog.core_tools.EXECUTE_CODE`, execution delegates to the injected legacy invoker."""

from __future__ import annotations

from llm.tool_catalog.core_tools import EXECUTE_CODE as _LEGACY

from ..registry import ToolApproval, ToolDefinition, ToolDisplay
from ._legacy import delegate_to_invoker

PROMPT_SNIPPET = 'Python code execution with pandas, numpy, matplotlib available. Use plt.savefig() not plt.show().'

TOOL = ToolDefinition(
    id=_LEGACY.id,
    display=ToolDisplay(name=_LEGACY.name),
    description=_LEGACY.description,
    input_schema=_LEGACY.input_schema,
    handler=delegate_to_invoker(_LEGACY.id),
    approval=ToolApproval.AUTO,
    prompt_snippet=PROMPT_SNIPPET,
)
