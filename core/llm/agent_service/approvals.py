"""Approval records for the tool calls a turn stops on, stored in the database.

The agent core opens an approval per gated call and pauses; the record
it hands the frontend must be addressable, because the answer comes
back as a separate request. `MCPToolApproval` is where such a record
lives, so this port writes one per gated call and reports it under the
primary key the database issued.

A gated call's `ToolDefinition.id` is not what an `MCPTool` row is
keyed on: V1 offers a tool under the bare name its server publishes,
which happens to match, but V2 offers it under a server-prefixed id
(see `agent_service.mcp_port`), which never would. `ToolDisplay.name`
is the one field both endpoints always carry unchanged from the
server's own tool name, so the row is looked up by that, plus the
server's name where the tool carries one, to keep two same-named tools
on different servers apart.

A call whose tool still resolves to no `MCPTool` row -- a built-in
catalog tool, or one an MCP server no longer surfaces -- gets a record
with no primary key to answer against. Rather than pausing a turn
nobody can release, the port reports no approval for it, which the
loop reads as a call to leave pending.
"""

from __future__ import annotations

import json
import logging
from typing import List, Sequence, Tuple

from asgiref.sync import sync_to_async

from ..agent_core.events import Approval, JsonDict, ToolCall
from ..agent_core.graph.ports import PENDING_APPROVAL_STATUS
from ..agent_core.registry import ToolDefinition

# Child of the configured "llm" logger (see sterna/logging.py APP_LOGGERS).
logger = logging.getLogger(__name__)


class StoredToolApprovals:
    """Opens one `MCPToolApproval` row per gated call, scoped to one chat."""

    def __init__(self, *, user_id: str, session_id: str = "") -> None:
        self._user_id = user_id
        self._session_id = session_id

    async def open(
        self, requests: Sequence[Tuple[ToolCall, ToolDefinition]]
    ) -> List[Approval]:
        return await sync_to_async(self._open_sync)(list(requests))

    def _open_sync(
        self, requests: Sequence[Tuple[ToolCall, ToolDefinition]]
    ) -> List[Approval]:
        from authentication.models import User
        from mcp.models import MCPToolApproval

        user = User.objects.filter(id=self._user_id).first()
        if user is None:
            return []

        opened: List[Approval] = []
        for call, definition in requests:
            tool = _mcp_tool_of(definition)
            if tool is None:
                logger.warning(
                    "agent_service.approval_tool_missing",
                    extra={"tool_id": definition.id},
                )
                continue
            record = MCPToolApproval.objects.create(
                user=user,
                tool=tool,
                session_id=self._session_id,
                proposed_arguments=_arguments_of(call),
                status=MCPToolApproval.ApprovalStatus.PENDING,
                scope=MCPToolApproval.ApprovalScope.ONCE,
            )
            opened.append(
                Approval(
                    id=str(record.pk),
                    tool_id=str(tool.pk),
                    tool_name=tool.name,
                    tool_description=tool.description or definition.description,
                    server_name=_server_name(tool, definition),
                    arguments=_arguments_of(call),
                    status=PENDING_APPROVAL_STATUS,
                )
            )
        return opened


def _mcp_tool_of(definition: ToolDefinition):
    """The `MCPTool` row a gated call's definition was minted from, if any.

    Matched on the tool's own published name -- the one field
    `ToolDisplay.name` always holds unchanged, regardless of which
    endpoint's naming strategy shaped `definition.id`. Narrowed by
    server name first, so two servers with a same-named tool are not
    conflated; a definition whose server name does not (or no longer)
    match any row -- `mcp_port` falls back to a placeholder server name
    when a tool's own server cannot be read, and a server can be
    renamed after a definition was minted from it -- still resolves
    against the name alone rather than reporting no tool at all.
    """

    from mcp.models import MCPTool

    by_name = MCPTool.objects.filter(name=definition.display.name)
    if definition.display.server_name:
        by_server = by_name.filter(server__name=definition.display.server_name).first()
        if by_server is not None:
            return by_server
    return by_name.first()


def _server_name(tool, definition: ToolDefinition) -> str:
    server = getattr(tool, "server", None)
    return getattr(server, "name", None) or definition.display.server_name or ""


def _arguments_of(call: ToolCall) -> JsonDict:
    try:
        decoded = json.loads(call.function.arguments or "{}")
    except ValueError:
        return {}
    return decoded if isinstance(decoded, dict) else {}
