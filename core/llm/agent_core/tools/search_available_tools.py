"""Search Available Tools: the tool-discovery meta-tool V2's `tool_discovery`
system-prompt section (`prompts_v2.modular_prompts.STATIC_CORE_PROMPTS`)
mandates by name on every turn.

No entry exists for this tool in `llm.tool_catalog.core_tools`. Its
schema is transcribed verbatim from `TOOL_SEARCH_DEFINITION` in
`llm.tool_discovery.tool_search` rather than imported from there,
because that module imports `langchain_core.tools` at module scope —
pulling it in would drag LangChain into `agent_core`'s transitive
import closure. Execution delegates to the same tool id via the
injected legacy invoker (`llm.agent_service.tool_invoker`), which runs
the real `create_tool_search_tool` factory from that module.
`test_agent_core_tool_discovery_drift.py` guards this module against
drifting from that source.
"""

from __future__ import annotations

from ..registry import ToolApproval, ToolDefinition, ToolDisplay
from ._legacy import delegate_to_invoker

TOOL_ID = "search_available_tools"

TOOL = ToolDefinition(
    id=TOOL_ID,
    display=ToolDisplay(name="Search Available Tools"),
    description=(
        "Search for available tools that can help with your task. Use "
        "this to discover capabilities before attempting to use "
        "specific tools."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Description of what you need to do",
            },
            "category": {
                "type": "string",
                "description": "Optional category filter",
                "enum": [
                    "search",
                    "location",
                    "file_system",
                    "code",
                    "communication",
                    "productivity",
                    "data",
                    "media",
                ],
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum tools to return (1-50)",
                "default": 20,
                "minimum": 1,
                "maximum": 50,
            },
        },
        "required": ["query"],
    },
    handler=delegate_to_invoker(TOOL_ID),
    approval=ToolApproval.REQUIRED,
)
