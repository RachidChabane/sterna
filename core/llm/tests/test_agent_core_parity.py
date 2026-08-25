"""Parity: the agent core reproduces every committed golden transcript.

Each scenario drives `llm.agent_core.graph` with the generations its
golden fixture fed the legacy streaming path, renders the loop's typed
events through `llm.agent_core.sse`, rewrites the result into what the
legacy path would have put on the wire, normalizes it with the goldens'
own rules, and compares the bytes to the committed transcript.

Every rewrite is one declared `Divergence`, and a scenario's run fails
if a divergence it declares no longer changes anything: a difference
that closes must be removed from the declaration rather than left
standing as a silent allowance.
"""

import asyncio
import unittest
from typing import List, Sequence

import pytest

from llm.agent_core.events import StreamEvent
from llm.agent_core.graph import AgentLoop
from llm.agent_core.provider import ProviderMessage
from llm.tests.golden.harness import TRANSCRIPTS_DIR, TRANSCRIPT_SUFFIX, transcript_path
from llm.tests.golden.normalization import normalize
from llm.tests.parity import frames as wire
from llm.tests.parity.scenarios import PROMPT, ParityScenario, scenarios

pytestmark = pytest.mark.golden

USER_ROLE = "user"
THREAD_ID_PREFIX = "parity"


async def _run(scenario: ParityScenario) -> List[StreamEvent]:
    loop = AgentLoop(scenario.build_dependencies())
    stream = loop.start(
        [ProviderMessage(role=USER_ROLE, content=PROMPT)],
        thread_id=f"{THREAD_ID_PREFIX}-{scenario.name}",
    )
    return [event async for event in stream]


def _golden_names() -> List[str]:
    return sorted(
        path.name[: -len(TRANSCRIPT_SUFFIX)]
        for path in TRANSCRIPTS_DIR.glob(f"*{TRANSCRIPT_SUFFIX}")
    )


class AgentCoreGoldenParityTests(unittest.TestCase):
    """Byte-exact parity between the agent loop and the legacy transcripts."""

    def test_every_golden_transcript_has_a_scenario(self):
        self.assertEqual(sorted(scenario.name for scenario in scenarios()), _golden_names())

    def test_every_declared_divergence_states_a_reason(self):
        unexplained = [
            f"{scenario.name}:{divergence.name}"
            for scenario in scenarios()
            for divergence in scenario.divergences
            if not divergence.name or not divergence.reason
        ]
        self.assertEqual(unexplained, [], "every divergence must state its reason")

    def test_each_scenario_reproduces_its_golden_transcript(self):
        diverged = []
        for scenario in scenarios():
            with self.subTest(scenario=scenario.name):
                try:
                    self._assert_parity(scenario)
                except AssertionError:
                    diverged.append(scenario.name)
                    raise
        self.assertEqual(diverged, [], "scenarios that diverged from their golden")

    # --- Comparison -------------------------------------------------

    def _assert_parity(self, scenario: ParityScenario) -> None:
        emitted = wire.frames_of(asyncio.run(_run(scenario)))
        self.assertTrue(
            emitted,
            f"{scenario.name} produced no events; there is nothing to compare.",
        )

        rendered = normalize(wire.render(self._as_legacy(scenario, emitted)))
        expected = transcript_path(scenario.name).read_bytes()
        self.assertEqual(
            rendered.decode("utf-8"),
            expected.decode("utf-8"),
            f"The agent core's stream diverged from {scenario.name} beyond what "
            "that scenario declares.",
        )

    def _as_legacy(
        self, scenario: ParityScenario, emitted: Sequence[wire.Frame]
    ) -> List[wire.Frame]:
        """Apply every declared divergence, failing on one that no longer bites."""

        current = list(emitted)
        for divergence in scenario.divergences:
            rewritten = divergence.applied_to(current, emitted)
            self.assertNotEqual(
                rewritten,
                current,
                f"{scenario.name} declares the divergence {divergence.name!r}, "
                "which no longer changes anything. Remove the declaration.",
            )
            current = rewritten
        return current


if __name__ == "__main__":
    unittest.main()
