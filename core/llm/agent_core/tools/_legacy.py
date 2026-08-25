"""Shared handler factory for a tool whose execution still lives in legacy code.

Every tool in this package that wraps pre-Phase-4 logic (the catalog
tools in `llm.tool_catalog.core_tools`, the handlers dispatched by
`llm.http_tool_executor`) reaches that logic the same way: by calling
back through the `LegacyToolInvoker` port on the execution context,
naming itself by tool id. `delegate_to_invoker` builds that handler
once so each tool module states only its id, not the call.
"""

from __future__ import annotations

from ..events import JsonDict
from ..registry import ToolExecutionContext, ToolHandler


def delegate_to_invoker(tool_id: str) -> ToolHandler:
    async def handler(arguments: JsonDict, context: ToolExecutionContext) -> JsonDict:
        return await context.invoker.invoke(tool_id, arguments, context)

    return handler
