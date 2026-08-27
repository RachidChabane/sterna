"""The V2 wire actually surfaces an MCP passthrough call's approval pause.

`run_every_call_except_mcp` (policy.py) stops the graph on an
MCP-surfaced call; these tests confirm that pause reaches a V2 client
as a real `tool_call_request` frame naming the approval and a `done`
frame marked `awaiting_approval` -- the same rendering a V1 client
already gets for a gated catalog tool, since both endpoints render
through the same `agent_core.sse` payload builder. Independent of the
golden-parity suite (`test_agent_service_v2_wire.py`) so this never
touches a golden fixture.
"""

from __future__ import annotations

import json
import unittest

from llm.agent_core.graph import LocalApprovals
from llm.agent_core.registry import ToolApproval
from llm.agent_service.accounting import TurnAccounting
from llm.agent_service.policy import run_every_call_except_mcp
from llm.agent_service.v2_wire import V2Wire
from llm.tests.agent_core_doubles import (
    AgentLoop,
    RecordingTool,
    ScriptedProvider,
    dependencies,
    text_generation,
    tool_call,
    tool_call_generation,
    user_message,
)

CALL_ID = "call-mcp"
TOOL_ID = "mcp_docs_search_docs"


async def _mcp_gate_frames() -> str:
    mcp_tool = RecordingTool(
        TOOL_ID, approval=ToolApproval.AUTO, server_name="Docs MCP"
    )
    provider = ScriptedProvider(
        [
            tool_call_generation("gen-1", tool_call(CALL_ID, TOOL_ID, query="x")),
            text_generation("gen-2", "done"),
        ]
    )
    loop = AgentLoop(
        dependencies(
            provider,
            [mcp_tool],
            approvals=LocalApprovals(),
            approval_policy=run_every_call_except_mcp,
        )
    )
    wire = V2Wire(
        TurnAccounting(), display_names={}, file_tools_enabled=False
    )
    frames = [
        frame
        async for frame in wire.frames(
            loop.start([user_message("hello")], thread_id="thread-v2-mcp-gate")
        )
    ]
    return "".join(frames)


def _frame_payload(raw: str, event_name: str) -> dict:
    lines = raw.splitlines()
    for index, line in enumerate(lines):
        if line == f"event: {event_name}":
            return json.loads(lines[index + 1].removeprefix("data: "))
    raise AssertionError(f"no {event_name!r} frame in:\n{raw}")


class V2WireSurfacesMcpApprovalTests(unittest.IsolatedAsyncioTestCase):
    async def test_the_wire_emits_a_tool_call_request_frame_for_the_paused_call(self):
        raw = await _mcp_gate_frames()

        payload = _frame_payload(raw, "tool_call_request")
        self.assertEqual([call["id"] for call in payload["tool_calls"]], [CALL_ID])
        self.assertEqual(len(payload["approvals"]), 1)
        self.assertEqual(payload["approvals"][0]["status"], "pending")

    async def test_the_wire_s_done_frame_reports_the_turn_as_awaiting_approval(self):
        raw = await _mcp_gate_frames()

        payload = _frame_payload(raw, "done")
        self.assertTrue(payload["awaiting_approval"])
        self.assertEqual(payload["approval_count"], 1)


if __name__ == "__main__":
    unittest.main()
