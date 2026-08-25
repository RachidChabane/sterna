"""Parity: the V1 wire adapter reproduces every V1 golden transcript.

Each V1 scenario feeds the agent loop the generations its golden
fixture fed the streaming path, renders the loop's events through
`llm.agent_service.v1_wire`, normalizes the result with the goldens'
own rules, and compares the bytes to the committed transcript. No
rewrite stands between the two: what the adapter emits is what the
endpoint puts on the wire.
"""

import asyncio
import json
import unittest
from typing import List

import pytest

from llm.agent_core.events import (
    DoneEvent,
    ErrorEvent,
    FileToolExecutedEvent,
    FinishReason,
    ToolCall,
    ToolCallFunction,
    Usage,
    UsageUpdateEvent,
)
from llm.agent_core.graph import AgentLoop
from llm.agent_core.provider import ProviderMessage
from llm.agent_service.accounting import TurnAccounting
from llm.agent_service.v1_wire import V1Wire, error_frame
from llm.tests.golden.harness import transcript_path
from llm.tests.golden.normalization import normalize
from llm.tests.parity.scenarios import PROMPT, ParityScenario, scenarios

pytestmark = pytest.mark.golden

USER_ROLE = "user"
THREAD_ID_PREFIX = "v1-wire"
V1_SCENARIO_PREFIX = "v1_"

NON_ASCII_RESULT = {"success": True, "content": "café — déjà vu"}


def _v1_scenarios() -> List[ParityScenario]:
    return [
        scenario for scenario in scenarios() if scenario.name.startswith(V1_SCENARIO_PREFIX)
    ]


async def _render(scenario: ParityScenario) -> bytes:
    loop = AgentLoop(scenario.build_dependencies())
    wire = V1Wire(TurnAccounting())
    events = loop.start(
        [ProviderMessage(role=USER_ROLE, content=PROMPT)],
        thread_id=f"{THREAD_ID_PREFIX}-{scenario.name}",
    )
    frames = [frame async for frame in wire.frames(events)]
    return "".join(frames).encode("utf-8")


async def _frames_of(events) -> List[str]:
    async def _stream():
        for event in events:
            yield event

    wire = V1Wire(TurnAccounting())
    return [frame async for frame in wire.frames(_stream())]


class V1WireGoldenParityTests(unittest.TestCase):
    """Byte-exact parity between the V1 wire adapter and the V1 transcripts."""

    def test_every_v1_transcript_has_a_scenario(self):
        self.assertEqual(
            sorted(scenario.name for scenario in _v1_scenarios()),
            [
                "v1_catalog_tool_approval_gate",
                "v1_file_and_catalog_tools_in_one_turn",
                "v1_file_tool_round_trip",
                "v1_plain_text_completion",
                "v1_provider_error_mid_stream",
            ],
        )

    def test_each_scenario_reproduces_its_golden_transcript(self):
        for scenario in _v1_scenarios():
            with self.subTest(scenario=scenario.name):
                rendered = normalize(asyncio.run(_render(scenario)))
                expected = transcript_path(scenario.name).read_bytes()
                self.assertEqual(
                    rendered.decode("utf-8"),
                    expected.decode("utf-8"),
                    f"The V1 wire adapter diverged from {scenario.name}.",
                )


class V1WireShapeTests(unittest.TestCase):
    """The parts of the V1 format no committed transcript exercises."""

    def test_tool_result_content_keeps_non_ascii_characters(self):
        call = ToolCall(
            id="call-1", function=ToolCallFunction(name="read_file", arguments="{}")
        )
        event = FileToolExecutedEvent(
            tool_calls=[call],
            results=[
                {
                    "tool_call": {
                        "id": call.id,
                        "type": call.type,
                        "function": {"name": "read_file", "arguments": "{}"},
                    },
                    "result": NON_ASCII_RESULT,
                    "success": True,
                }
            ],
        )

        frames = asyncio.run(_frames_of([event]))

        payload = json.loads(frames[0].split("data: ", 1)[1])
        self.assertEqual(
            payload["results"][0]["content"],
            json.dumps(NON_ASCII_RESULT, ensure_ascii=False),
        )

    def test_done_reports_the_generations_cost_without_the_tools(self):
        """A V1 `done` shows what the model cost, never what a tool spent."""

        call = ToolCall(
            id="call-1", function=ToolCallFunction(name="run_bash", arguments="{}")
        )
        events = [
            UsageUpdateEvent(
                usage=Usage(prompt_tokens=100, completion_tokens=20, total_tokens=120),
                cost=0.0003,
                prompt_cost=0.0001,
                completion_cost=0.0002,
                generation_id="gen-1",
                generation_ids=["gen-1"],
            ),
            FileToolExecutedEvent(
                tool_calls=[call],
                results=[
                    {
                        "tool_call": {
                            "id": call.id,
                            "type": call.type,
                            "function": {"name": "run_bash", "arguments": "{}"},
                        },
                        "result": {"success": True, "cost_usd": 0.5},
                        "success": True,
                    }
                ],
            ),
            DoneEvent(
                model="fixture/golden-model",
                finish_reason=FinishReason.STOP,
                usage=Usage(prompt_tokens=100, completion_tokens=20, total_tokens=120),
                cost=0.0003,
            ),
        ]

        frames = asyncio.run(_frames_of(events))

        done = json.loads(frames[-1].split("data: ", 1)[1])
        self.assertEqual(done["cost"], 0.0003)
        self.assertNotIn("tool_cost", done)

    def test_error_frame_carries_the_message_alone(self):
        event = ErrorEvent(
            error="The AI service is temporarily unavailable. Please try again.",
            detail="502 Bad Gateway",
            extra={"status_code": 502},
        )

        payload = json.loads(error_frame(event).split("data: ", 1)[1])

        self.assertEqual(
            payload, {"error": "The AI service is temporarily unavailable. Please try again."}
        )


if __name__ == "__main__":
    unittest.main()
