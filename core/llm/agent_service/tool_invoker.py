"""Running a catalog tool through the implementation that already owns it.

A `ToolDefinition` under `llm.agent_core.tools` states a tool's schema,
label and approval requirement and delegates the work itself to the
`LegacyToolInvoker` on its execution context. The implementations live
in `llm.langchain_file_tools`, `llm.brave_search_tools`,
`llm.image_tools` and their siblings, as callables bound by name and
reading the request from the ContextVars
`llm.agent.streaming.request_context` publishes.

This invoker dispatches by that name. Running the same callables the
LangChain path runs is what keeps a tool's behaviour -- its sandbox
routing, its own quota deduction, its result shape -- identical
whichever stack served the turn.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Mapping

from ..agent_core.events import JsonDict
from ..agent_core.registry import ToolExecutionContext

# Child of the configured "llm" logger (see sterna/logging.py APP_LOGGERS).
logger = logging.getLogger(__name__)

UNKNOWN_TOOL_ERROR = "Tool '{name}' is not available for this request."

SUCCESS_FIELD = "success"
CONTENT_FIELD = "content"
ERROR_FIELD = "error"
RESULT_FIELD = "result"


class BoundToolInvoker:
    """Invokes the callable bound under a tool's name for this request."""

    def __init__(self, tools_by_name: Mapping[str, Any]) -> None:
        self._tools_by_name = dict(tools_by_name)

    async def invoke(
        self, tool_id: str, arguments: JsonDict, context: ToolExecutionContext
    ) -> JsonDict:
        tool = self._tools_by_name.get(tool_id)
        if tool is None:
            logger.error("agent_service.tool_not_bound", extra={"tool_id": tool_id})
            return {
                SUCCESS_FIELD: False,
                ERROR_FIELD: UNKNOWN_TOOL_ERROR.format(name=tool_id),
            }
        return _as_result(await tool.ainvoke(dict(arguments)))


def _as_result(returned: Any) -> JsonDict:
    """One tool's return value, as the mapping the loop reports.

    A tool that answers with text rather than a payload is reported as
    a successful `content` result, which is the shape the wire already
    carries for those tools.
    """

    if isinstance(returned, str):
        try:
            decoded = json.loads(returned)
        except json.JSONDecodeError:
            return {CONTENT_FIELD: returned, SUCCESS_FIELD: True}
        return decoded if isinstance(decoded, dict) else {RESULT_FIELD: decoded}
    if isinstance(returned, dict):
        return returned
    return {RESULT_FIELD: returned}
