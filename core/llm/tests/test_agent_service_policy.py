"""Unit tests for `llm.agent_service.policy`: what V2's approval policy answers.

`run_every_call_except_mcp` is what stands between an MCP passthrough
tool call and running unattended in the V2 stream. These tests pin the
classification directly against the policy function, then drive a full
turn through `AgentLoop` to confirm an MCP-surfaced call actually
pauses for sign-off -- mirroring the catalog-tool gate UX -- while a
platform tool with the identical `approval` default keeps running
without one, and that both answers (approved, denied) carry the paused
call forward the same way a normally gated call does.
"""

from __future__ import annotations

import unittest

from llm.agent_core.events import EventType
from llm.agent_core.graph import (
    AgentLoop,
    ApprovalDecision,
    LocalApprovals,
    ToolApprovalDecision,
)
from llm.agent_core.registry import ToolApproval
from llm.agent_service.policy import run_every_call_except_mcp
from llm.tests.agent_core_doubles import (
    RecordingTool,
    ScriptedProvider,
    all_of,
    collect,
    dependencies,
    event_names,
    first_of,
    run_turn,
    text_generation,
    tool_call,
    tool_call_generation,
)


class RunEveryCallExceptMcpTests(unittest.TestCase):
    """The policy function in isolation, against its own definition/call inputs."""

    def test_a_tool_with_no_server_name_is_auto_even_when_its_own_default_is_required(self):
        tool = RecordingTool("run_bash", approval=ToolApproval.REQUIRED)
        call, definition = self._call_and_definition(tool)

        self.assertIs(run_every_call_except_mcp(definition, call), ToolApproval.AUTO)

    def test_a_tool_with_a_server_name_is_required_even_when_its_own_default_is_auto(self):
        tool = RecordingTool(
            "search_docs", approval=ToolApproval.AUTO, server_name="Docs MCP"
        )
        call, definition = self._call_and_definition(tool)

        self.assertIs(run_every_call_except_mcp(definition, call), ToolApproval.REQUIRED)

    def _call_and_definition(self, tool: RecordingTool):
        call = tool_call(f"call-{tool.tool_id}", tool.tool_id, x=1)
        return call, tool.definition()


def _turn_with(tool: RecordingTool, *, tool_call_id: str):
    provider = ScriptedProvider(
        [
            tool_call_generation(
                "gen-1", tool_call(tool_call_id, tool.tool_id, query="x")
            ),
            text_generation("gen-2", "done"),
        ]
    )
    loop = AgentLoop(
        dependencies(
            provider,
            [tool],
            approvals=LocalApprovals(),
            approval_policy=run_every_call_except_mcp,
        )
    )
    return loop, provider


class McpPassthroughGatingTests(unittest.IsolatedAsyncioTestCase):
    """Under the V2 policy, an MCP-surfaced tool call halts for sign-off."""

    async def test_an_mcp_call_pauses_the_turn_with_an_approval_request(self):
        mcp_tool = RecordingTool(
            "search_docs", approval=ToolApproval.AUTO, server_name="Docs MCP"
        )
        loop, provider = _turn_with(mcp_tool, tool_call_id="call-mcp")

        events = await run_turn(loop, thread_id="thread-mcp-gate")

        self.assertEqual(
            event_names(events),
            [
                EventType.GENERATION_ID,
                EventType.TOOL_CALL_REQUEST,
                EventType.DONE,
            ],
        )
        self.assertEqual(mcp_tool.calls, [])
        request = first_of(events, EventType.TOOL_CALL_REQUEST)
        self.assertEqual([call.id for call in request.tool_calls], ["call-mcp"])
        self.assertTrue(first_of(events, EventType.DONE).awaiting_approval)

    async def test_a_platform_tool_with_the_same_default_still_runs_unattended(self):
        platform_tool = RecordingTool("run_bash", approval=ToolApproval.REQUIRED)
        loop, provider = _turn_with(platform_tool, tool_call_id="call-platform")

        events = await run_turn(loop, thread_id="thread-platform-no-gate")

        self.assertEqual(all_of(events, EventType.TOOL_CALL_REQUEST), [])
        self.assertEqual(platform_tool.calls, [{"query": "x"}])

    async def test_approving_the_paused_mcp_call_runs_it_and_finishes_the_turn(self):
        mcp_tool = RecordingTool(
            "search_docs", approval=ToolApproval.AUTO, server_name="Docs MCP"
        )
        loop, provider = _turn_with(mcp_tool, tool_call_id="call-mcp")
        await run_turn(loop, thread_id="thread-mcp-approve")

        await collect(
            loop.resume(
                [
                    ToolApprovalDecision(
                        tool_call_id="call-mcp", decision=ApprovalDecision.APPROVED
                    )
                ],
                thread_id="thread-mcp-approve",
            )
        )

        self.assertEqual(mcp_tool.calls, [{"query": "x"}])
        self.assertEqual(provider.call_count, 2)

    async def test_denying_the_paused_mcp_call_never_runs_it(self):
        mcp_tool = RecordingTool(
            "search_docs", approval=ToolApproval.AUTO, server_name="Docs MCP"
        )
        loop, provider = _turn_with(mcp_tool, tool_call_id="call-mcp")
        await run_turn(loop, thread_id="thread-mcp-deny")

        await collect(
            loop.resume(
                [
                    ToolApprovalDecision(
                        tool_call_id="call-mcp", decision=ApprovalDecision.DENIED
                    )
                ],
                thread_id="thread-mcp-deny",
            )
        )

        self.assertEqual(mcp_tool.calls, [])

    async def test_an_unanswered_mcp_call_counts_as_denied(self):
        mcp_tool = RecordingTool(
            "search_docs", approval=ToolApproval.AUTO, server_name="Docs MCP"
        )
        loop, provider = _turn_with(mcp_tool, tool_call_id="call-mcp")
        await run_turn(loop, thread_id="thread-mcp-unanswered")

        await collect(loop.resume([], thread_id="thread-mcp-unanswered"))

        self.assertEqual(mcp_tool.calls, [])


if __name__ == "__main__":
    unittest.main()
