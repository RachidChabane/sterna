"""Coverage: the SSE adapter answers for every event the loop can emit.

`events.EVENT_PAYLOAD_TYPES` is the full vocabulary of the stream. An
event type the adapter has no branch for would raise only when a turn
happened to emit one, so one sample of every type is rendered here: the
sample set must cover the vocabulary exactly, each sample must render,
and each frame must name the event it carries.
"""

import json
import unittest
from typing import Dict

from llm.agent_core import sse
from llm.agent_core.events import (
    EVENT_PAYLOAD_TYPES,
    CodingAgentCompletedEvent,
    CodingAgentQuestionEvent,
    CodingAgentStepEvent,
    ContentEvent,
    ContextCompactedEvent,
    ContextTrimmedEvent,
    DoneEvent,
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
    StreamEvent,
    ToolCall,
    ToolCallFunction,
    ToolCallRequestEvent,
    Usage,
    UsageUpdateEvent,
    WebSource,
    WebSourcesEvent,
)

SAMPLE_USAGE = Usage(prompt_tokens=1, completion_tokens=2, total_tokens=3)
SAMPLE_CALL = ToolCall(
    id="call-1", function=ToolCallFunction(name="read_file", arguments="{}")
)


def _samples() -> Dict[EventType, StreamEvent]:
    """One instance of every payload type, keyed by the name it goes out under."""

    events: tuple = (
        GenerationIdEvent(generation_id="generation-1"),
        ContentEvent(content="visible"),
        ReasoningEvent(content="thinking"),
        ImageEvent(image="data:image/png;base64,AAAA"),
        HeartbeatEvent(tool="read_file", elapsed_seconds=1),
        UsageUpdateEvent(
            usage=SAMPLE_USAGE,
            cost=0.1,
            prompt_cost=0.05,
            completion_cost=0.05,
            generation_id="generation-1",
            generation_ids=["generation-1"],
        ),
        WebSourcesEvent(sources=[WebSource(url="https://example.invalid", title="Example")]),
        PreviewStartedEvent(port=8000, command="pnpm dev", pid=42),
        ContextTrimmedEvent(trimmed_count=1, remaining_messages=9),
        ContextCompactedEvent(original_messages=9, compacted_messages=4, tokens_saved=100),
        ToolCallRequestEvent(approvals=[], tool_calls=[SAMPLE_CALL]),
        FileToolExecutingEvent(tool_calls=[SAMPLE_CALL]),
        FileToolExecutedEvent(tool_calls=[SAMPLE_CALL], results=[{"success": True}]),
        CodingAgentStepEvent(
            step_index=0, type="tool", tool="run_bash", content="ls", timestamp=None
        ),
        CodingAgentQuestionEvent(question="Which branch?", options=["main"]),
        CodingAgentCompletedEvent(
            success=True,
            summary="done",
            files_modified=[],
            files_created=[],
            duration_ms=10,
            total_tokens=20,
            steps=[],
        ),
        DoneEvent(
            model="fixture/model",
            finish_reason=FinishReason.STOP,
            usage=SAMPLE_USAGE,
            cost=0.1,
        ),
        ErrorEvent(error="failed", detail="upstream said no"),
    )
    return {event.event_type: event for event in events}


class AgentCoreSseCoverageTests(unittest.TestCase):
    def test_every_event_name_maps_to_a_payload_type(self):
        self.assertEqual(sorted(EVENT_PAYLOAD_TYPES), sorted(EventType))

    def test_the_samples_cover_the_whole_vocabulary(self):
        self.assertEqual(sorted(_samples()), sorted(EVENT_PAYLOAD_TYPES))

    def test_every_event_renders_a_frame_naming_itself(self):
        unrendered = []
        for event_type, event in _samples().items():
            frame = sse.render_event(event)
            if not frame.startswith(f"event: {event_type}\ndata: "):
                unrendered.append(str(event_type))
            self.assertTrue(frame.endswith("\n\n"))
            json.loads(frame.split("data: ", 1)[1])
        self.assertEqual(unrendered, [], "frames whose event line names something else")

    def test_a_field_with_no_value_is_left_out(self):
        payload = sse.event_payload(HeartbeatEvent())

        self.assertEqual(payload, {})


if __name__ == "__main__":
    unittest.main()
