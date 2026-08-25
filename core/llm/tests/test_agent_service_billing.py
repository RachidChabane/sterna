"""Billing on the V2 stream served by the agent core.

A turn is billed at two moments, and both are exercised here. A turn
that reaches its `done` event writes the aggregate usage row from the
turn's own totals, before that event leaves the wire. A turn whose
client goes away mid-stream never reaches `done`, so the generations
it already spent are settled from the disconnect handler instead --
and a turn already settled is not settled twice.
"""

import unittest
from unittest.mock import AsyncMock, patch

from rest_framework.test import APIClient, APITestCase

from llm.agent.feature_flags import AgentFeatureFlags
from llm.agent_service.accounting import TurnAccounting
from llm.agent_service.endpoint import _settle_abandoned
from llm.agent_service.session import V2TurnSession
from llm.tests.conftest import make_billing_user, seed_billing_plan
from llm.tests.golden.harness import (
    BILLING_PLAN_NAME,
    CONVERSATION_ID,
    GENERATION_ID,
    MODEL_ID,
    capture_sse,
    seed_model_catalog,
)
from llm.tests.golden.test_v2_stream_complete_agent_core import (
    AGENT_CORE_HEADER,
    STOP,
    STREAM_URL,
    NoWaitRateLimiter,
    content_chunk,
    generation_id_chunk,
    usage_chunk,
)
from llm.agent_core.provider import ProviderDoneChunk
from llm.tests.agent_core_doubles import ScriptedProvider

USER_ID = "user-billing"
CHAT_ID = "chat-billing"
FIRST_GENERATION_ID = "genid-first"
SECOND_GENERATION_ID = "genid-second"

ENQUEUE_TARGET = "llm.tasks.enqueue_abort_settlement"

PROMPT_TOKENS = 120
COMPLETION_TOKENS = 40
NO_TOOL_COST = 0.0


def _session(accounting: TurnAccounting, *, is_openrouter: bool = True) -> V2TurnSession:
    async def key() -> str:
        return "sk-test"

    return V2TurnSession(
        model=MODEL_ID,
        model_name=None,
        is_openrouter=is_openrouter,
        flags=AgentFeatureFlags(),
        tools=[],
        accounting=accounting,
        openrouter_key_for_tools=key,
    )


class AbortSettlementTests(unittest.TestCase):
    """What an abandoned V2 stream bills."""

    def test_settles_every_generation_the_turn_spent(self):
        accounting = TurnAccounting()
        accounting.record_generation_id(FIRST_GENERATION_ID)
        accounting.record_generation_id(SECOND_GENERATION_ID)

        with patch(ENQUEUE_TARGET) as enqueue:
            _settle_abandoned(_session(accounting), user_id=USER_ID, chat_id=CHAT_ID)

        enqueue.assert_called_once_with(
            user_id=USER_ID,
            generation_ids=[FIRST_GENERATION_ID, SECOND_GENERATION_ID],
            model_id=MODEL_ID,
            chat_id=CHAT_ID,
        )

    def test_a_settled_turn_is_not_settled_again(self):
        accounting = TurnAccounting(settled=True)
        accounting.record_generation_id(FIRST_GENERATION_ID)

        with patch(ENQUEUE_TARGET) as enqueue:
            _settle_abandoned(_session(accounting), user_id=USER_ID, chat_id=CHAT_ID)

        enqueue.assert_not_called()

    def test_a_turn_that_bypassed_openrouter_is_not_settled_against_it(self):
        accounting = TurnAccounting()
        accounting.record_generation_id(FIRST_GENERATION_ID)

        with patch(ENQUEUE_TARGET) as enqueue:
            _settle_abandoned(
                _session(accounting, is_openrouter=False),
                user_id=USER_ID,
                chat_id=CHAT_ID,
            )

        enqueue.assert_not_called()

    def test_cancelling_marks_the_turn_for_the_loop_to_stop(self):
        session = _session(TurnAccounting())
        self.assertFalse(session.is_cancelled)
        session.cancel()
        self.assertTrue(session.is_cancelled)


class TurnAccountingTests(unittest.TestCase):
    """What the figures a turn is billed on accumulate."""

    def test_tool_cost_excludes_what_a_tool_already_billed_itself(self):
        accounting = TurnAccounting()
        accounting.record_tool_results([
            {
                "tool_call": {"function": {"name": "generate_image"}},
                "result": {"cost_usd": 0.04, "provider": "openrouter"},
            },
            {
                "tool_call": {"function": {"name": "brave_web_search"}},
                "result": {"cost_usd": 0.01, "provider": "openrouter"},
            },
        ])
        self.assertAlmostEqual(accounting.tool_cost, 0.05)
        self.assertAlmostEqual(accounting.image_generation_cost, 0.04)

    def test_a_generation_id_is_remembered_once(self):
        accounting = TurnAccounting()
        accounting.record_generation_id(FIRST_GENERATION_ID)
        accounting.record_generation_id(FIRST_GENERATION_ID)
        self.assertEqual(accounting.generation_ids, [FIRST_GENERATION_ID])
        self.assertEqual(accounting.last_generation_id, FIRST_GENERATION_ID)


class SessionAccountingRebindTests(unittest.TestCase):
    """What the endpoint reads after the turn moved to another model."""

    def test_the_endpoint_reads_the_attempt_now_running(self):
        first = TurnAccounting()
        first.record_generation_id(FIRST_GENERATION_ID)
        session = _session(first)

        second = TurnAccounting()
        second.record_generation_id(SECOND_GENERATION_ID)
        session.rebind_accounting(second)

        self.assertEqual(session.all_generation_ids, [SECOND_GENERATION_ID])


class AggregateSettlementTests(APITestCase):
    """What a completed V2 turn writes its usage row from."""

    def setUp(self):
        seed_model_catalog()
        plan = seed_billing_plan(BILLING_PLAN_NAME)
        self.user = make_billing_user("v2-agent-core-billing@example.com", plan)
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_the_turn_totals_reach_the_aggregate_usage_row(self):
        provider = ScriptedProvider([
            [
                generation_id_chunk(GENERATION_ID),
                content_chunk("The notes list two open items."),
                usage_chunk(PROMPT_TOKENS, COMPLETION_TOKENS),
                ProviderDoneChunk(finish_reason=STOP),
            ]
        ])
        record = AsyncMock(return_value=0.0)

        patches = [
            patch("llm.views.RateLimiter", NoWaitRateLimiter),
            patch(
                "llm.views.get_user_instructions",
                return_value={"enabled": False, "content": ""},
            ),
            patch(
                "llm.services.api_key_resolver.resolve_endpoint",
                return_value=("sk-golden-fixture", None, "platform", None),
            ),
            patch(
                "llm.agent_service.dependencies.OpenRouterProvider",
                return_value=provider,
            ),
            patch(
                "llm.agent.cost_ledger.CostLedger.record_chat_aggregate_usage",
                record,
            ),
        ]
        started = []
        try:
            for active in patches:
                active.start()
                started.append(active)
            response = self.client.post(
                STREAM_URL,
                {
                    "model": MODEL_ID,
                    "messages": [{"role": "user", "content": "Summarize the notes."}],
                    "conversation_id": CONVERSATION_ID,
                },
                format="json",
                **{AGENT_CORE_HEADER: "on"},
            )
            capture_sse(response)
        finally:
            for active in reversed(started):
                active.stop()

        record.assert_awaited_once_with(
            PROMPT_TOKENS, COMPLETION_TOKENS, NO_TOOL_COST, NO_TOOL_COST
        )


if __name__ == "__main__":
    unittest.main()
