"""The tools one V1 chat request offers, and the executor behind them.

V1 offers the model two groups and no others: the sandboxed workspace
tools `llm.file_tools_integration.get_file_tools` describes, when the
request asked for file tools, and the user's MCP tools under the bare
names an MCP server publishes, when it asked for those. Reading the
first group from `get_file_tools` rather than restating it keeps one
answer to "which tools does a V1 request have", whichever surface asks.

Every one of those tools already has a typed definition under
`llm.agent_core.tools`, carrying the schema the model is shown and the
approval requirement V1 holds it to. The definitions are looked up
there and the execution is delegated back to `execute_file_tool_call`,
which is where the sandbox routing, the model attribution and the
error shape of a V1 tool call live.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from asgiref.sync import sync_to_async

from ..agent.feature_flags import AgentFeatureFlags
from ..agent_core.events import JsonDict
from ..agent_core.mcp_bridge import MCPToolSource
from ..agent_core.registry import (
    ToolDefinition,
    ToolExecutionContext,
    ToolRegistry,
    discover_tools,
)

# Child of the configured "llm" logger (see sterna/logging.py APP_LOGGERS).
logger = logging.getLogger(__name__)

FUNCTION_FIELD = "function"
NAME_FIELD = "name"
CONTENT_FIELD = "content"
SUCCESS_FIELD = "success"
ERROR_FIELD = "error"

AUTH_TOKEN_KEY = "auth_token"
GITHUB_TOKEN_KEY = "github_token"
MODEL_METADATA_KEY = "model_metadata"

UNATTRIBUTED_CALL_ID = ""
"""The id handed to the executor for the message this invoker discards.

The executor echoes it into a tool-role message; the loop pairs a
result with the call that produced it on its own, so nothing reads the
echo back.
"""


def file_tool_ids() -> List[str]:
    """The workspace tools a V1 request with file tools offers the model.

    A workspace contract that cannot be read leaves the turn with no
    file tools rather than with no answer, which is what a request
    whose tools failed to load has always got.
    """

    from ..file_tools_integration import get_file_tools

    try:
        return [tool[FUNCTION_FIELD][NAME_FIELD] for tool in get_file_tools()]
    except Exception:
        logger.error("agent_service.v1_file_tools_unavailable", exc_info=True)
        return []


def file_tool_definitions() -> List[ToolDefinition]:
    """The typed definition of each workspace tool V1 offers.

    A name with no definition under `llm.agent_core.tools` is left out
    rather than offered without a schema; the drift guard over these
    two sources is what keeps that list empty.
    """

    catalog = discover_tools()
    definitions: List[ToolDefinition] = []
    for name in file_tool_ids():
        definition = catalog.get(name)
        if definition is None:
            logger.error("agent_service.v1_file_tool_undefined", extra={"tool_id": name})
            continue
        definitions.append(definition)
    return definitions


async def build_v1_tool_registry(
    flags: AgentFeatureFlags,
    *,
    user_id: str,
    mcp_tools: Optional[MCPToolSource] = None,
) -> ToolRegistry:
    """Everything this V1 request's switches entitle it to call."""

    definitions: List[ToolDefinition] = []
    if flags.file_tools:
        definitions.extend(file_tool_definitions())
    if mcp_tools is not None and flags.mcp_tools:
        definitions.extend(await _mcp_definitions(mcp_tools, user_id))
    return ToolRegistry(definitions)


async def _mcp_definitions(
    mcp_tools: MCPToolSource, user_id: str
) -> List[ToolDefinition]:
    try:
        return await mcp_tools.discover(user_id)
    except Exception:
        logger.error("agent_service.mcp_tools_unavailable", exc_info=True)
        return []


class SandboxToolInvoker:
    """Runs one V1 tool call through the sandbox executor V1 runs it through.

    The executor answers with the tool-role message V1 sends back to
    the model, carrying the result as a JSON string. The loop works in
    result payloads and renders the message itself, so the string is
    decoded here and re-serialized on the wire.
    """

    def __init__(
        self,
        *,
        auth_token: Optional[str] = None,
        github_token: Optional[str] = None,
        model_metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        self._auth_token = auth_token
        self._github_token = github_token
        self._model_metadata = model_metadata

    async def invoke(
        self, tool_id: str, arguments: JsonDict, context: ToolExecutionContext
    ) -> JsonDict:
        from ..file_tools_integration import execute_file_tool_call

        message = await sync_to_async(execute_file_tool_call)(
            tool_call_id=UNATTRIBUTED_CALL_ID,
            tool_name=tool_id,
            tool_arguments=dict(arguments),
            user_id=context.user_id,
            conversation_id=context.conversation_id,
            chat_id=context.chat_id,
            sync_mode=context.sync_mode,
            auth_token=self._auth_token,
            github_token=self._github_token,
            model_metadata=self._model_metadata,
        )
        return _result_of(message)


def _result_of(message: JsonDict) -> JsonDict:
    """The payload carried by one tool-role message from the executor."""

    content = message.get(CONTENT_FIELD)
    if not isinstance(content, str):
        return {SUCCESS_FIELD: False, ERROR_FIELD: "The tool returned no content."}
    try:
        decoded = json.loads(content)
    except ValueError:
        return {SUCCESS_FIELD: True, CONTENT_FIELD: content}
    return decoded if isinstance(decoded, dict) else {CONTENT_FIELD: decoded}
