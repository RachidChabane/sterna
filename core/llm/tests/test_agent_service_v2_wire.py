"""Parity: the V2 wire adapter reproduces every V2 golden transcript.

Each V2 scenario feeds the agent loop the generations its golden
fixture fed the streaming path, renders the loop's events through
`llm.agent_service.v2_wire`, normalizes the result with the goldens'
own rules, and compares the bytes to the committed transcript. No
rewrite stands between the two: what the adapter emits is what the
endpoint puts on the wire.
"""

import asyncio
import unittest
from typing import List, Mapping

import pytest

from llm.agent_core.graph import AgentLoop
from llm.agent_core.provider import ProviderMessage
from llm.agent_service.accounting import TurnAccounting
from llm.agent_service.v2_wire import V2Wire
from llm.tests.golden.harness import transcript_path
from llm.tests.golden.normalization import normalize
from llm.tests.parity.scenarios import DISPLAY_NAMES, PROMPT, ParityScenario, scenarios

pytestmark = pytest.mark.golden

USER_ROLE = "user"
THREAD_ID_PREFIX = "v2-wire"
V2_SCENARIO_PREFIX = "v2_"

FILE_TOOLS_ENABLED_SCENARIOS = frozenset(
    {"v2_file_tool_round_trip", "v2_file_and_catalog_tools_in_one_turn"}
)
"""The V2 scenarios whose request enabled file tools."""


def _v2_scenarios() -> List[ParityScenario]:
    return [
        scenario for scenario in scenarios() if scenario.name.startswith(V2_SCENARIO_PREFIX)
    ]


async def _render(scenario: ParityScenario, display_names: Mapping[str, str]) -> bytes:
    loop = AgentLoop(scenario.build_dependencies())
    wire = V2Wire(
        TurnAccounting(),
        display_names=display_names,
        file_tools_enabled=scenario.name in FILE_TOOLS_ENABLED_SCENARIOS,
    )
    events = loop.start(
        [ProviderMessage(role=USER_ROLE, content=PROMPT)],
        thread_id=f"{THREAD_ID_PREFIX}-{scenario.name}",
    )
    frames = [frame async for frame in wire.frames(events)]
    return "".join(frames).encode("utf-8")


class V2WireGoldenParityTests(unittest.TestCase):
    """Byte-exact parity between the V2 wire adapter and the V2 transcripts."""

    def test_every_v2_transcript_has_a_scenario(self):
        self.assertEqual(
            sorted(scenario.name for scenario in _v2_scenarios()),
            [
                "v2_catalog_tool_round_trip",
                "v2_file_and_catalog_tools_in_one_turn",
                "v2_file_tool_round_trip",
                "v2_plain_text_completion",
                "v2_provider_error_mid_stream",
            ],
        )

    def test_each_scenario_reproduces_its_golden_transcript(self):
        for scenario in _v2_scenarios():
            with self.subTest(scenario=scenario.name):
                rendered = normalize(asyncio.run(_render(scenario, DISPLAY_NAMES)))
                expected = transcript_path(scenario.name).read_bytes()
                self.assertEqual(
                    rendered.decode("utf-8"),
                    expected.decode("utf-8"),
                    f"The V2 wire adapter diverged from {scenario.name}.",
                )


if __name__ == "__main__":
    unittest.main()
