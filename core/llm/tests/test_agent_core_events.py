"""Unit tests for the typed streaming-event model in `llm.agent_core.events`."""

import unittest

from llm.agent_core.events import (
    EVENT_PAYLOAD_TYPES,
    Approval,
    CodingAgentCompletedEvent,
    CodingAgentQuestionEvent,
    CodingAgentStepEvent,
    ContentEvent,
    ContextCompactedEvent,
    ContextTrimmedEvent,
    DoneEvent,
    ErrorCode,
    ErrorEvent,
    EventType,
    FileToolExecutedEvent,
    FileToolExecutingEvent,
    FinishReason,
    GenerationIdEvent,
    HeartbeatEvent,
    ImageEvent,
    PreviewStartedEvent,
    ReasoningEvent,
    ToolCall,
    ToolCallFunction,
    ToolCallRequestEvent,
    Usage,
    UsageUpdateEvent,
    WebSource,
    WebSourcesEvent,
)


class EventPayloadTypeRegistryTests(unittest.TestCase):
    def test_every_event_type_has_a_payload_class(self):
        self.assertEqual(set(EVENT_PAYLOAD_TYPES), set(EventType))

    def test_each_payload_class_is_keyed_by_its_own_event_type(self):
        for event_type, payload_type in EVENT_PAYLOAD_TYPES.items():
            self.assertEqual(payload_type.event_type, event_type)

    def test_payload_classes_are_frozen(self):
        event = ContentEvent(content="hello")
        with self.assertRaises(AttributeError):
            event.content = "changed"  # type: ignore[misc]


class SimplePayloadShapeTests(unittest.TestCase):
    def test_generation_id_event(self):
        event = GenerationIdEvent(generation_id="genid-1")
        self.assertEqual(event.event_type, EventType.GENERATION_ID)
        self.assertEqual(event.generation_id, "genid-1")

    def test_content_and_reasoning_events_share_a_content_field(self):
        content = ContentEvent(content="The notes ")
        reasoning = ReasoningEvent(content="thinking...")
        self.assertEqual(content.event_type, EventType.CONTENT)
        self.assertEqual(reasoning.event_type, EventType.REASONING)
        self.assertEqual(content.content, "The notes ")
        self.assertEqual(reasoning.content, "thinking...")

    def test_image_event(self):
        event = ImageEvent(image="data:image/png;base64,...")
        self.assertEqual(event.event_type, EventType.IMAGE)

    def test_heartbeat_event_defaults_to_a_generic_keepalive(self):
        generic = HeartbeatEvent()
        tool_specific = HeartbeatEvent(tool="brave_web_search", elapsed_seconds=3)
        self.assertIsNone(generic.tool)
        self.assertIsNone(generic.elapsed_seconds)
        self.assertEqual(tool_specific.tool, "brave_web_search")
        self.assertEqual(tool_specific.elapsed_seconds, 3)


class UsageAndCostEventTests(unittest.TestCase):
    def test_usage_update_event(self):
        event = UsageUpdateEvent(
            usage=Usage(prompt_tokens=120, completion_tokens=40, total_tokens=160),
            cost=0.0002,
            prompt_cost=0.00012,
            completion_cost=0.00008,
            generation_id="genid-1",
            generation_ids=["genid-1"],
        )
        self.assertEqual(event.event_type, EventType.USAGE_UPDATE)
        self.assertEqual(event.usage.total_tokens, 160)
        self.assertEqual(event.generation_ids, ["genid-1"])

    def test_usage_update_event_generation_ids_defaults_to_empty(self):
        event = UsageUpdateEvent(
            usage=Usage(0, 0, 0),
            cost=0.0,
            prompt_cost=0.0,
            completion_cost=0.0,
            generation_id="genid-1",
        )
        self.assertEqual(event.generation_ids, [])

    def test_web_sources_event(self):
        event = WebSourcesEvent(
            sources=[WebSource(url="https://example.invalid/sterna", title="Sterna streaming")]
        )
        self.assertEqual(event.event_type, EventType.WEB_SOURCES)
        self.assertEqual(event.sources[0].title, "Sterna streaming")


class ToolEventTests(unittest.TestCase):
    def _web_search_tool_call(self) -> ToolCall:
        return ToolCall(
            id="toolcall-web-search",
            function=ToolCallFunction(
                name="brave_web_search", arguments='{"query": "sterna streaming"}'
            ),
        )

    def test_tool_call_request_event_carries_approvals_and_calls(self):
        approval = Approval(
            id="<approval-pk-1>",
            tool_id="<mcp-tool-pk-1>",
            tool_name="brave_web_search",
            tool_description="Search the web for current information.",
            server_name="Fixture Search Server",
            arguments={"query": "sterna streaming"},
            status="pending",
        )
        event = ToolCallRequestEvent(approvals=[approval], tool_calls=[self._web_search_tool_call()])
        self.assertEqual(event.event_type, EventType.TOOL_CALL_REQUEST)
        self.assertEqual(event.approvals[0].status, "pending")

    def test_file_tool_executing_and_executed_events(self):
        tool_call = self._web_search_tool_call()
        executing = FileToolExecutingEvent(tool_calls=[tool_call])
        executed = FileToolExecutedEvent(
            tool_calls=[tool_call],
            results=[{"tool_call": {"id": tool_call.id}, "result": {"success": True}, "success": True}],
        )
        self.assertEqual(executing.event_type, EventType.FILE_TOOL_EXECUTING)
        self.assertEqual(executed.event_type, EventType.FILE_TOOL_EXECUTED)
        self.assertEqual(executed.results[0]["success"], True)


class ContextManagementEventTests(unittest.TestCase):
    def test_context_trimmed_event(self):
        event = ContextTrimmedEvent(trimmed_count=1, remaining_messages=4)
        self.assertEqual(event.event_type, EventType.CONTEXT_TRIMMED)

    def test_context_compacted_event_optional_fields_default_to_none(self):
        event = ContextCompactedEvent(original_messages=10, compacted_messages=4, tokens_saved=500)
        self.assertIsNone(event.original_tokens)
        self.assertIsNone(event.compression_ratio)

    def test_preview_started_event(self):
        event = PreviewStartedEvent(port=3000, command="npm run dev", pid=1234)
        self.assertEqual(event.event_type, EventType.PREVIEW_STARTED)


class CodingAgentEventTests(unittest.TestCase):
    def test_coding_agent_step_event(self):
        event = CodingAgentStepEvent(
            step_index=0, type="text", tool=None, content="Reading files", timestamp="2026-08-25T00:00:00Z"
        )
        self.assertEqual(event.event_type, EventType.CODING_AGENT_STEP)

    def test_coding_agent_question_event(self):
        event = CodingAgentQuestionEvent(
            question="Overwrite existing file?",
            options=[{"label": "Yes", "description": "Replace the file."}],
        )
        self.assertEqual(event.event_type, EventType.CODING_AGENT_QUESTION)

    def test_coding_agent_completed_event(self):
        event = CodingAgentCompletedEvent(
            success=True,
            summary="Refactored the module.",
            files_modified=["core/llm/views.py"],
            files_created=[],
            duration_ms=1234,
            total_tokens=500,
            steps=[{"type": "text", "content": "..."}],
        )
        self.assertEqual(event.event_type, EventType.CODING_AGENT_COMPLETED)
        self.assertTrue(event.success)


class TerminalEventTests(unittest.TestCase):
    def test_done_event_for_a_completed_turn(self):
        event = DoneEvent(
            model="fixture/golden-model",
            finish_reason=FinishReason.STOP,
            usage=Usage(prompt_tokens=120, completion_tokens=40, total_tokens=160),
            cost=0.00032,
            prompt_cost=0.00012,
            completion_cost=0.0002,
        )
        self.assertEqual(event.event_type, EventType.DONE)
        self.assertEqual(event.finish_reason, FinishReason.STOP)

    def test_done_event_for_a_cancelled_turn_has_zero_usage(self):
        event = DoneEvent(
            model="fixture/golden-model",
            finish_reason=FinishReason.CANCELLED,
            usage=Usage(0, 0, 0),
            cost=0,
        )
        self.assertEqual(event.finish_reason, FinishReason.CANCELLED)
        self.assertEqual(event.usage.total_tokens, 0)

    def test_done_event_awaiting_approval(self):
        tool_call = ToolCall(
            id="toolcall-web-search",
            function=ToolCallFunction(name="brave_web_search", arguments="{}"),
        )
        event = DoneEvent(
            model="fixture/golden-model",
            finish_reason=FinishReason.TOOL_CALLS,
            usage=Usage(120, 40, 160),
            cost=0.00032,
            tool_calls=[tool_call],
            awaiting_approval=True,
            approval_count=1,
        )
        self.assertTrue(event.awaiting_approval)
        self.assertEqual(event.approval_count, 1)

    def test_error_event_without_a_code(self):
        event = ErrorEvent(error="API Error", detail="Upstream provider returned 502 Bad Gateway")
        self.assertEqual(event.event_type, EventType.ERROR)
        self.assertIsNone(event.code)

    def test_error_event_with_a_code(self):
        event = ErrorEvent(
            error="Model does not support tools",
            detail="The model 'fixture/model' does not support function calling/tools.",
            code=ErrorCode.NO_TOOL_SUPPORT,
        )
        self.assertEqual(event.code, ErrorCode.NO_TOOL_SUPPORT)


if __name__ == "__main__":
    unittest.main()
