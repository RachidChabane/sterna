"""Get Tool Details: the tool-discovery meta-tool V2's `tool_discovery`
system-prompt section (`prompts_v2.modular_prompts.STATIC_CORE_PROMPTS`)
mandates by name on every turn, alongside `search_available_tools`.

No entry exists for this tool in `llm.tool_catalog.core_tools`. Its
schema is transcribed verbatim from `GET_TOOL_DETAILS_DEFINITION` in
`llm.tool_discovery.tool_search` rather than imported from there,
because that module imports `langchain_core.tools` at module scope —
pulling it in would drag LangChain into `agent_core`'s transitive
import closure. Execution delegates to the same tool id via the
injected legacy invoker (`llm.agent_service.tool_invoker`), which runs
the real `create_get_tool_details_tool` factory from that module.
`test_agent_core_tool_discovery_drift.py` guards this module against
drifting from that source.
"""

from __future__ import annotations

from ..registry import ToolApproval, ToolDefinition, ToolDisplay
from ._legacy import delegate_to_invoker

TOOL_ID = "get_tool_details"

TOOL = ToolDefinition(
    id=TOOL_ID,
    display=ToolDisplay(name="Get Tool Details"),
    description=(
        "Get full parameter schema and examples for a specific tool. "
        "Use after search_available_tools when you need complete "
        "details before calling a tool."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "function_name": {
                "type": "string",
                "description": (
                    "The exact function_name from search_available_tools "
                    "results"
                ),
            },
        },
        "required": ["function_name"],
    },
    handler=delegate_to_invoker(TOOL_ID),
    approval=ToolApproval.REQUIRED,
)
