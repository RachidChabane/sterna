"""Matrix coverage tests for task 7 billing wiring.

Every billing code path that task 7 added or flipped from unwired to
wired (per-feature UsageLog creation, cost attribution, quota
enforcement) has at least one assertion in this file. Failures mean
billing wiring has regressed.

Test pattern (load-bearing — do not deviate):
    Use sync `def test_*` methods. When the call site is async, wrap
    with `async_to_sync(coro)(...)`. Django's TestCase does NOT run
    `async def test_*` methods — pytest collects them but the coroutine
    is never awaited, the test silently passes, and the assertion never
    runs. See plan section L0.
"""

from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch, AsyncMock

from asgiref.sync import async_to_sync
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from usage_quota.models import (
    FeatureType,
    ServicePricing,
    ServiceType,
    SubscriptionPlan,
    UsageLog,
    UserSubscription,
)


User = get_user_model()


# Mirror of migration 0005's PRICING_ROWS — duplicated here so the test
# suite is independent of whether `--reuse-db` skipped the migration.
EXPECTED_PRICING_ROWS = [
    {"service": "mcp_tool_invocation", "model_id": "",
     "price_per_request": Decimal("0.001000")},
    {"service": "google_maps", "model_id": "geocoding",
     "price_per_request": Decimal("0.005000")},
    {"service": "google_maps", "model_id": "directions",
     "price_per_request": Decimal("0.005000")},
    {"service": "google_maps", "model_id": "places_nearby",
     "price_per_request": Decimal("0.032000")},
    {"service": "google_maps", "model_id": "places_details",
     "price_per_request": Decimal("0.017000")},
    {"service": "google_maps", "model_id": "air_quality",
     "price_per_request": Decimal("0.005000")},
    {"service": "google_maps", "model_id": "street_view",
     "price_per_request": Decimal("0.007000")},
    {"service": "image_generation", "model_id": "",
     "price_per_request": Decimal("0.020000")},
    {"service": "kb_embedding", "model_id": "",
     "price_per_1m_input_tokens": Decimal("0.130000")},
    {"service": "kb_query", "model_id": "",
     "price_per_1m_input_tokens": Decimal("0.130000")},
    {"service": "code_session", "model_id": "",
     "price_per_request": Decimal("0.000000")},
]


class BillingCoverageBase(TestCase):
    """Shared fixtures for matrix-coverage tests."""

    @classmethod
    def setUpTestData(cls):
        cls.plan, _ = SubscriptionPlan.objects.get_or_create(
            name="bcov-test",
            defaults={
                "display_name": "Coverage Test",
                "weekly_limit_usd": Decimal("10.00"),
                "session_limit_usd": Decimal("5.00"),
                "features": {},
            },
        )
        cls._seed_pricing_rows()

    @classmethod
    def _seed_pricing_rows(cls):
        now = timezone.now()
        for row in EXPECTED_PRICING_ROWS:
            defaults = {k: v for k, v in row.items()
                        if k not in ("service", "model_id")}
            defaults.update({"is_active": True, "effective_from": now})
            existing = (
                ServicePricing.objects
                .filter(service=row["service"], model_id=row["model_id"])
                .order_by("-effective_from").first()
            )
            if existing is None:
                ServicePricing.objects.create(
                    service=row["service"],
                    model_id=row["model_id"],
                    **defaults,
                )
            else:
                for k, v in defaults.items():
                    setattr(existing, k, v)
                existing.save()

    def setUp(self):
        self.user = User.objects.create_user(
            email=f"u-{self.id()}@test.local",
            password="x",
        )
        UserSubscription.objects.create(
            user=self.user, plan=self.plan, is_active=True,
        )

    def assertBilled(self, *, service, feature, min_cost_usd=Decimal("0"),
                     count=1):
        rows = UsageLog.objects.filter(
            user=self.user, service=service, feature=feature,
        )
        self.assertEqual(
            rows.count(), count,
            f"Expected {count} UsageLog row(s) for service={service} "
            f"feature={feature}, got {rows.count()}: "
            f"{list(rows.values('service', 'feature', 'cost_usd'))}"
        )
        if rows.exists():
            self.assertGreaterEqual(rows.first().cost_usd, min_cost_usd)

    def assertNotBilled(self, *, service=None, feature=None):
        qs = UsageLog.objects.filter(user=self.user)
        if service:
            qs = qs.filter(service=service)
        if feature:
            qs = qs.filter(feature=feature)
        self.assertEqual(
            qs.count(), 0,
            f"Expected NO UsageLog rows matching the filter, got "
            f"{list(qs.values('service', 'feature', 'cost_usd'))}"
        )


class TestMigrationSmoke(BillingCoverageBase):
    """Pricing rows from migration 0005 exist for all new keys."""

    def test_seed_pricing_rows_exist(self):
        for row in EXPECTED_PRICING_ROWS:
            self.assertTrue(
                ServicePricing.objects.filter(
                    service=row["service"], model_id=row["model_id"],
                    is_active=True,
                ).exists(),
                f"Missing pricing for {row['service']}/{row['model_id']}",
            )


class TestMCPBilling(BillingCoverageBase):
    """Matrix row #27. Patches `UnifiedMCPRegistry.execute_tool_by_name`
    on `mcp.unified_registry` — the live module used by
    `tool_discovery_adapter.py:48`. Patching `mcp.registry.MCPRegistry`
    would be a silent no-op.
    """

    def setUp(self):
        super().setUp()
        # The cascading guard (task 10) gates MCP behind the 'mcp' plan
        # flag BEFORE the USD quota check; enable it so these tests
        # exercise the quota/billing wiring itself, not the flag gate.
        self.plan.features = {"mcp": True}
        self.plan.save(update_fields=["features"])

    @patch("mcp.unified_registry.UnifiedMCPRegistry.execute_tool_by_name",
           new_callable=AsyncMock)
    def test_mcp_invocation_bills(self, mock_exec):
        from mcp.tool_discovery_adapter import MCPToolDiscoveryAdapter
        mock_exec.return_value = {"success": True, "result": "ok"}
        adapter = MCPToolDiscoveryAdapter()
        async_to_sync(adapter.execute_mcp_tool)(
            user_id=str(self.user.id),
            tool_id="mcp_notion_create-page",
            arguments={},
        )
        self.assertBilled(
            service=ServiceType.MCP_TOOL_INVOCATION,
            feature=FeatureType.CHAT,
            min_cost_usd=Decimal("0.001"),
        )

    @patch("mcp.unified_registry.UnifiedMCPRegistry.execute_tool_by_name",
           new_callable=AsyncMock)
    def test_mcp_failure_does_not_bill(self, mock_exec):
        from mcp.tool_discovery_adapter import MCPToolDiscoveryAdapter
        mock_exec.return_value = {"success": False, "error": "tool_error"}
        adapter = MCPToolDiscoveryAdapter()
        async_to_sync(adapter.execute_mcp_tool)(
            user_id=str(self.user.id),
            tool_id="mcp_notion_create-page",
            arguments={},
        )
        self.assertNotBilled(service=ServiceType.MCP_TOOL_INVOCATION)

    @patch("mcp.unified_registry.UnifiedMCPRegistry.execute_tool_by_name",
           new_callable=AsyncMock)
    def test_mcp_pre_check_blocks_over_quota_user(self, mock_exec):
        # Drain the user's weekly quota with a single big synthetic row.
        UsageLog.objects.create(
            user=self.user,
            service=ServiceType.OPENROUTER,
            feature=FeatureType.CHAT,
            cost_usd=Decimal("10.000"),
        )
        # Window-start must be set for `check_quota` to count the row —
        # and it must predate the row's auto_now_add timestamp, or the
        # `timestamp__gte=window_start` filter excludes it.
        window_start = timezone.now() - timedelta(minutes=1)
        sub = self.user.subscription
        sub.weekly_window_start = window_start
        sub.session_window_start = window_start
        sub.save(update_fields=["weekly_window_start", "session_window_start"])

        from mcp.tool_discovery_adapter import MCPToolDiscoveryAdapter
        adapter = MCPToolDiscoveryAdapter()
        result = async_to_sync(adapter.execute_mcp_tool)(
            user_id=str(self.user.id),
            tool_id="mcp_notion_create-page",
            arguments={},
        )
        self.assertEqual(result.get("success"), False)
        self.assertEqual(result.get("error"), "quota_exceeded")
        mock_exec.assert_not_called()
        self.assertNotBilled(service=ServiceType.MCP_TOOL_INVOCATION)


class TestGoogleMapsBilling(BillingCoverageBase):
    """Matrix row #19 — one test per endpoint."""

    def _run_tool_with_user(self, tool_callable, args, mock_response):
        from llm.google_maps_tools import GOOGLE_MAPS_USER_CONTEXT
        GOOGLE_MAPS_USER_CONTEXT.set({"user_id": str(self.user.id)})
        try:
            with patch(
                "llm.google_maps_tools.call_google_maps_service",
                new_callable=AsyncMock,
            ) as mock_call:
                mock_call.return_value = mock_response
                async_to_sync(tool_callable.ainvoke)(args)
        finally:
            GOOGLE_MAPS_USER_CONTEXT.set(None)

    def test_geocode_address_bills(self):
        from llm.google_maps_tools import geocode_address
        self._run_tool_with_user(
            geocode_address,
            {"address": "1 Main St"},
            '{"success": true, "lat": 0, "lng": 0}',
        )
        self.assertBilled(
            service=ServiceType.GOOGLE_MAPS,
            feature=FeatureType.CHAT,
        )
        row = UsageLog.objects.filter(
            user=self.user, service=ServiceType.GOOGLE_MAPS,
        ).first()
        self.assertEqual(row.model_id, "geocoding")

    def test_get_directions_bills(self):
        from llm.google_maps_tools import get_directions
        self._run_tool_with_user(
            get_directions,
            {"origin": "A", "destination": "B"},
            '{"success": true, "routes": []}',
        )
        row = UsageLog.objects.filter(
            user=self.user, service=ServiceType.GOOGLE_MAPS,
        ).first()
        self.assertEqual(row.model_id, "directions")

    def test_get_air_quality_bills(self):
        from llm.google_maps_tools import get_air_quality
        self._run_tool_with_user(
            get_air_quality,
            {"location": "1.0,2.0"},
            '{"success": true, "aqi": 50}',
        )
        row = UsageLog.objects.filter(
            user=self.user, service=ServiceType.GOOGLE_MAPS,
        ).first()
        self.assertEqual(row.model_id, "air_quality")

    def test_failed_request_does_not_bill(self):
        from llm.google_maps_tools import geocode_address
        self._run_tool_with_user(
            geocode_address,
            {"address": "1 Main St"},
            '{"success": false, "error": "boom"}',
        )
        self.assertNotBilled(service=ServiceType.GOOGLE_MAPS)


class TestCodeSessionBilling(BillingCoverageBase):
    """Matrix rows #8-#11.

    `_bill_code_session` is the single bill site for coding-agent runs.
    The chat-row accumulator dedup is verified indirectly by ensuring the
    helper writes a dedicated `CODE_SESSION/CODE_SESSION` row.
    """

    def _make_context(self):
        # Lightweight stand-in matching the attributes _bill_code_session reads.
        class _Ctx:
            pass
        ctx = _Ctx()
        ctx.user_id = str(self.user.id)
        ctx.chat_id = "chat-abc"
        return ctx

    def test_bill_code_session_writes_code_session_row(self):
        from llm.agent_tool_handlers import _bill_code_session
        ctx = self._make_context()
        async_to_sync(_bill_code_session)(
            ctx, 0.05, "anthropic/claude-sonnet-4", "chat-abc",
        )
        self.assertBilled(
            service=ServiceType.CODE_SESSION,
            feature=FeatureType.CODE_SESSION,
            min_cost_usd=Decimal("0.05"),
        )

    def test_bill_code_session_zero_cost_skipped(self):
        from llm.agent_tool_handlers import _bill_code_session
        ctx = self._make_context()
        async_to_sync(_bill_code_session)(
            ctx, 0.0, "anthropic/claude-sonnet-4", "chat-abc",
        )
        self.assertNotBilled(service=ServiceType.CODE_SESSION)

    def test_bill_code_session_missing_user_skipped(self):
        from llm.agent_tool_handlers import _bill_code_session
        class _Ctx:
            user_id = None
            chat_id = None
        async_to_sync(_bill_code_session)(
            _Ctx(), 0.05, "anthropic/claude-sonnet-4", "",
        )
        self.assertNotBilled(service=ServiceType.CODE_SESSION)


class TestCodingAgentDedupGuard(BillingCoverageBase):
    """Matrix row #8 corollary — `CODING_AGENT_TOOL_NAMES` is the
    contract the chat-row accumulator dedup depends on. Pin its
    membership so future contributors can't accidentally rename a tool
    without updating the dedup guard.
    """

    def test_constant_contains_all_four_tools(self):
        from llm.agent_tool_handlers import CODING_AGENT_TOOL_NAMES
        self.assertEqual(
            CODING_AGENT_TOOL_NAMES,
            frozenset({
                "coding_agent",
                "plan_implementation",
                "implement_plan",
                "edit_plan",
            }),
        )


class TestKnowledgeBaseBilling(BillingCoverageBase):
    """Matrix rows #35-#37. Routing through `BillingService.record_usage`
    fires the window-start side effect via `quota_service.deduct_usage`.
    """

    def test_kb_embedding_records_and_starts_window(self):
        from knowledge_base.tasks import _log_indexing_usage

        sub = self.user.subscription
        self.assertIsNone(sub.weekly_window_start)

        _log_indexing_usage(
            user=self.user,
            document_id="doc-1",
            token_count=10_000,
            cost_usd=Decimal("0.001"),
            chunk_count=3,
            model_id="text-embedding-3-large",
        )
        self.assertBilled(
            service=ServiceType.KNOWLEDGE_BASE_EMBEDDING,
            feature=FeatureType.KNOWLEDGE_BASE,
            min_cost_usd=Decimal("0.001"),
        )
        sub.refresh_from_db()
        self.assertIsNotNone(sub.weekly_window_start,
                             "weekly_window_start was not set by record_usage")

    def test_kb_query_records_and_starts_window(self):
        from knowledge_base.services.query import KnowledgeQueryService

        sub = self.user.subscription
        self.assertIsNone(sub.weekly_window_start)

        # Construct just enough of the service to call its private helper.
        class _EmbStub:
            model = "text-embedding-3-large"
            billing_origin = "platform"

        service = KnowledgeQueryService.__new__(KnowledgeQueryService)
        # `embedding_service` is a property → set the backing attribute.
        service._embedding_service = _EmbStub()
        service._pricing_service = None
        service._log_query_usage(self.user, token_count=500,
                                 cost_usd=Decimal("0.0001"))

        self.assertBilled(
            service=ServiceType.KNOWLEDGE_BASE_QUERY,
            feature=FeatureType.KNOWLEDGE_BASE,
        )
        sub.refresh_from_db()
        self.assertIsNotNone(sub.weekly_window_start)


class TestVoiceRoomLLMBilling(BillingCoverageBase):
    """Matrix row #32 — LLMRouter records one OPENROUTER/VOICE_ROOM row."""

    def test_complete_records_voice_room_row(self):
        from voice_rooms.services.llm_router import LLMRouter

        router = LLMRouter(user=self.user)

        class _FakeResp:
            def raise_for_status(self):
                pass

            def json(self):
                return {
                    "choices": [{"message": {"content": "hi"}}],
                    "usage": {
                        "prompt_tokens": 100,
                        "completion_tokens": 50,
                    },
                }

        router._client = AsyncMock()
        router._client.post = AsyncMock(return_value=_FakeResp())

        async_to_sync(router.complete)(
            model="openai/gpt-4o-mini",
            messages=[{"role": "user", "content": "hi"}],
        )
        self.assertBilled(
            service=ServiceType.OPENROUTER,
            feature=FeatureType.VOICE_ROOM,
        )


# ---------------------------------------------------------------------------
# billing-fix 2026-07 — regression coverage for the adversarial audit items
# ---------------------------------------------------------------------------


def _make_ledger(user, model="clamp/test-model"):
    """The agent-core turn's cost ledger, wired to a real user."""
    from llm.agent.cost_ledger import CostLedger

    return CostLedger(lambda: str(user.id), model)


class TestImageGenSingleNetBill(BillingCoverageBase):
    """Matrix rows #20/#21 — an OpenRouter image generated inside the
    chat turn produces exactly ONE net bill: the per-image
    IMAGE_GENERATION row. The aggregate OPENROUTER/CHAT row must
    subtract the image-gen dollars (`image_gen_cost_in_bundle`).
    """

    @staticmethod
    def _image_tool_result(cost, provider="openrouter", name="generate_image"):
        return {
            "tool_call": {"id": "t1", "function": {"name": name}},
            "result": {"status": "success", "cost_usd": cost, "provider": provider},
            "success": True,
        }

    def test_classifier_marks_openrouter_image_gen(self):
        from llm.agent.cost_ledger import extract_billable_tool_costs

        tool_cost, image_cost = extract_billable_tool_costs(
            [self._image_tool_result(0.05)]
        )
        self.assertAlmostEqual(tool_cost, 0.05)
        self.assertAlmostEqual(image_cost, 0.05)

    def test_classifier_skips_non_openrouter_and_coding_tools(self):
        from llm.agent.cost_ledger import extract_billable_tool_costs

        tool_cost, image_cost = extract_billable_tool_costs([
            self._image_tool_result(0.05, provider="google_ai_studio"),
            self._image_tool_result(0.90, name="coding_agent"),
        ])
        self.assertEqual(tool_cost, 0.0)
        self.assertEqual(image_cost, 0.0)

    def test_openrouter_image_in_chat_bills_exactly_once_net(self):
        """Mocked-provider flow: the tool layer writes the per-image row
        (real `_record_billing`), then the chat settles through the real
        aggregate cost-ledger helper. The image dollars must appear in
        exactly one UsageLog row and quota must be decremented once.
        """
        from llm.agent.cost_ledger import extract_billable_tool_costs
        from llm.image_providers.base import ImageGenerationResult
        from llm.image_tools import _record_billing

        # 1) Tool layer (as generate_image does after a mocked provider call)
        result = ImageGenerationResult(
            image_data=b"png-bytes",
            mime_type="image/png",
            provider="openrouter",
            model="google/gemini-2.5-flash-image",
            cost_usd=Decimal("0.05"),
        )
        async_to_sync(_record_billing)(
            {"user_id": str(self.user.id)},
            result,
            "google/gemini-2.5-flash-image",
            billing_origin="platform",
        )

        # 2) Chat aggregate settlement (real cost-ledger billing helper)
        ledger = _make_ledger(self.user)
        tool_cost, image_cost = extract_billable_tool_costs(
            [self._image_tool_result(0.05)]
        )
        billed = async_to_sync(ledger.record_chat_aggregate_usage)(
            0, 0, tool_cost, image_cost
        )

        # Aggregate contributed nothing — image dollars live only in the
        # per-image IMAGE_GENERATION row.
        self.assertEqual(billed, 0.0)
        image_rows = UsageLog.objects.filter(
            user=self.user, service=ServiceType.IMAGE_GENERATION,
        )
        self.assertEqual(image_rows.count(), 1)
        self.assertEqual(image_rows.first().cost_usd, Decimal("0.05"))
        self.assertNotBilled(service=ServiceType.OPENROUTER)

    def test_chat_aggregate_row_bills_residual_tool_cost(self):
        """Matrix row #2 — the aggregate OPENROUTER/CHAT row still bills
        non-image tool cost (nothing else double-records it)."""
        ledger = _make_ledger(self.user)
        billed = async_to_sync(ledger.record_chat_aggregate_usage)(
            0, 0, 0.03, 0.0
        )
        self.assertAlmostEqual(billed, 0.03)
        self.assertBilled(
            service=ServiceType.OPENROUTER,
            feature=FeatureType.CHAT,
            min_cost_usd=Decimal("0.029"),
        )


class TestAbortSettlement(BillingCoverageBase):
    """Matrix row #6 — server-side settlement of aborted streams."""

    GEN_DATA = {
        "tokens_prompt": 100,
        "tokens_completion": 50,
        "total_cost": 0.0123,
        "model": "openai/gpt-4o-mini",
    }

    def _settle(self, gen_ids):
        from llm.tasks import settle_aborted_generations

        with patch(
            "llm.tasks.fetch_generation_data",
            return_value=dict(self.GEN_DATA),
        ), patch(
            "llm.services.api_key_resolver.get_api_key_for_user",
            return_value="sk-test",
        ), patch(
            "llm.services.api_key_resolver.resolve_with_origin",
            return_value=("sk-test", "platform"),
        ):
            return settle_aborted_generations(
                str(self.user.id), gen_ids, model_id="openai/gpt-4o-mini",
                session_id="chat-1",
            )

    def test_settlement_records_usage_once_idempotent_on_retry(self):
        first = self._settle(["gen-abc"])
        second = self._settle(["gen-abc"])  # simulated Celery retry/duplicate

        self.assertEqual(first["settled"], 1)
        self.assertEqual(second["settled"], 0)
        self.assertEqual(second["skipped"], 1)

        rows = UsageLog.objects.filter(
            user=self.user,
            service=ServiceType.OPENROUTER,
            request_id="gen-abc",
        )
        self.assertEqual(rows.count(), 1)
        row = rows.first()
        self.assertEqual(row.cost_usd, Decimal("0.0123"))
        self.assertEqual(row.feature, FeatureType.CHAT)
        self.assertEqual(row.extra_data.get("settlement"), "aborted_stream")

    def test_settlement_skips_iterations_already_billed_inline(self):
        """Direct-Client iterations bill inline with request_id=generation_id
        — the settlement task must not re-bill them."""
        UsageLog.objects.create(
            user=self.user,
            service=ServiceType.OPENROUTER,
            feature=FeatureType.CHAT,
            cost_usd=Decimal("0.010"),
            request_id="gen-inline",
        )
        result = self._settle(["gen-inline"])
        self.assertEqual(result["settled"], 0)
        self.assertEqual(result["skipped"], 1)
        self.assertEqual(
            UsageLog.objects.filter(
                user=self.user, request_id="gen-inline",
            ).count(),
            1,
        )

    def test_abort_path_enqueues_settlement_with_delay_and_marker(self):
        from django.core.cache import cache

        from llm import tasks as llm_tasks

        cache.delete(
            llm_tasks.ABORT_SETTLEMENT_CACHE_KEY.format(chat_id="chat-42")
        )
        with patch.object(
            llm_tasks.settle_aborted_generations, "apply_async",
        ) as mock_apply:
            ok = llm_tasks.enqueue_abort_settlement(
                user_id=str(self.user.id),
                generation_ids=["g1", "", "g2"],
                model_id="openai/gpt-4o-mini",
                chat_id="chat-42",
            )
        self.assertTrue(ok)
        mock_apply.assert_called_once()
        call_kwargs = mock_apply.call_args.kwargs
        self.assertEqual(
            call_kwargs["countdown"],
            llm_tasks.ABORT_SETTLEMENT_DELAY_SECONDS,
        )
        self.assertEqual(call_kwargs["args"], [str(self.user.id), ["g1", "g2"]])
        marker = cache.get(
            llm_tasks.ABORT_SETTLEMENT_CACHE_KEY.format(chat_id="chat-42")
        )
        self.assertIsNotNone(marker)
        self.assertEqual(marker["generation_ids"], ["g1", "g2"])
        cache.delete(
            llm_tasks.ABORT_SETTLEMENT_CACHE_KEY.format(chat_id="chat-42")
        )

    def test_enqueue_skips_when_no_generation_ids(self):
        from llm import tasks as llm_tasks

        with patch.object(
            llm_tasks.settle_aborted_generations, "apply_async",
        ) as mock_apply:
            ok = llm_tasks.enqueue_abort_settlement(
                user_id=str(self.user.id),
                generation_ids=[],
                chat_id="chat-x",
            )
        self.assertFalse(ok)
        mock_apply.assert_not_called()


class TestStoppedMessagePatchClamp(BillingCoverageBase):
    """Matrix row #6 — the client PATCH on a stopped message is advisory:
    the claimed cost is clamped/replaced server-side."""

    def setUp(self):
        super().setUp()
        from conversations.models import Chat, Conversation, Message

        self.conversation = Conversation.objects.create(
            user=self.user, name="clamp-test",
        )
        self.chat = Chat.objects.create(conversation=self.conversation)
        self.message = Message.objects.create(
            chat=self.chat,
            role="assistant",
            content={"text": "partial answer"},
            is_stopped=True,
            model_id="clamp/test-model",
        )
        from rest_framework.test import APIClient

        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.url = (
            f"/api/conversations/{self.conversation.id}"
            f"/chats/{self.chat.id}/messages/{self.message.id}/"
        )

    def _patch_billing(self, cost="999.0", prompt_tokens=100,
                       completion_tokens=50):
        return self.client.patch(
            self.url,
            {
                "cost": cost,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
            },
            format="json",
        )

    def test_client_patch_cannot_exceed_catalog_clamp(self):
        from conversations.views import MessageViewSet
        from llm.catalog_service import CatalogService

        response = self._patch_billing(cost="999.0")
        self.assertEqual(response.status_code, 200)

        rows = UsageLog.objects.filter(
            user=self.user, service=ServiceType.OPENROUTER,
        )
        self.assertEqual(rows.count(), 1)
        row = rows.first()

        expected_cap = (
            Decimal(str(
                CatalogService().estimate_cost_detailed(
                    model_id="clamp/test-model",
                    prompt_tokens=100,
                    completion_tokens=50,
                )["total_cost"]
            )) * MessageViewSet.STOPPED_COST_CLAMP_FACTOR
        )
        self.assertLess(row.cost_usd, Decimal("999"))
        self.assertEqual(
            row.cost_usd.quantize(Decimal("0.000001")),
            expected_cap.quantize(Decimal("0.000001")),
        )
        self.assertEqual(
            row.extra_data.get("accepted_source"), "catalog_price_clamp",
        )
        self.assertEqual(
            row.extra_data.get("client_claimed_cost"), "999.0",
        )

    def test_patch_uses_server_generation_lookup_when_ids_present(self):
        self.message.metadata = {"generation_ids": ["gen-x"]}
        self.message.save(update_fields=["metadata"])

        with patch(
            "llm.tasks.fetch_generation_data",
            return_value={
                "tokens_prompt": 10,
                "tokens_completion": 5,
                "total_cost": 0.002,
                "model": "clamp/test-model",
            },
        ), patch(
            "llm.services.api_key_resolver.get_api_key_for_user",
            return_value="sk-test",
        ):
            response = self._patch_billing(cost="999.0")
        self.assertEqual(response.status_code, 200)

        rows = UsageLog.objects.filter(
            user=self.user, service=ServiceType.OPENROUTER,
        )
        self.assertEqual(rows.count(), 1)
        row = rows.first()
        self.assertEqual(
            row.cost_usd.quantize(Decimal("0.000001")),
            Decimal("0.002000"),
        )
        self.assertEqual(row.request_id, "gen-x")
        self.assertEqual(
            row.extra_data.get("accepted_source"), "generation_lookup",
        )

    def test_patch_skipped_when_server_settlement_pending(self):
        from django.core.cache import cache

        from llm.tasks import ABORT_SETTLEMENT_CACHE_KEY

        key = ABORT_SETTLEMENT_CACHE_KEY.format(chat_id=str(self.chat.id))
        cache.set(key, {"generation_ids": ["g1"]}, timeout=60)
        try:
            response = self._patch_billing()
            self.assertEqual(response.status_code, 200)
            self.assertNotBilled(service=ServiceType.OPENROUTER)
        finally:
            cache.delete(key)

    def test_negative_claim_rejected(self):
        response = self._patch_billing(cost="-5.0")
        self.assertEqual(response.status_code, 200)
        self.assertNotBilled(service=ServiceType.OPENROUTER)


class TestVoiceDeductionHelpers(BillingCoverageBase):
    """Matrix rows #29a/#30a/#31/#38 — the TTS/STT deduction helpers each
    write exactly one UsageLog row."""

    def test_elevenlabs_tts_deduction_records(self):
        from voice_rooms.services.elevenlabs_tts import ElevenLabsTTSClient

        client = ElevenLabsTTSClient.__new__(ElevenLabsTTSClient)
        client._user = self.user
        client._session_id = "room-1"
        client._feature = FeatureType.VOICE_ROOM
        client._deduct_tts_usage(character_count=1000,
                                 model_id="eleven_flash_v2_5")
        self.assertBilled(
            service=ServiceType.ELEVENLABS_TTS,
            feature=FeatureType.VOICE_ROOM,
            min_cost_usd=Decimal("0.0001"),
        )

    def test_openai_tts_deduction_records(self):
        from voice_rooms.services.openai_tts_client import OpenAITTSClient

        client = OpenAITTSClient.__new__(OpenAITTSClient)
        client._user = self.user
        client._session_id = "room-1"
        client._deduct_tts_usage(character_count=1000, model_id="tts-1")
        self.assertBilled(
            service=ServiceType.OPENAI_TTS,
            feature=FeatureType.VOICE_ROOM,
            min_cost_usd=Decimal("0.0001"),
        )

    def test_deepgram_stt_deduction_records(self):
        from voice_rooms.services.deepgram_stt import DeepgramSTTClient

        client = DeepgramSTTClient.__new__(DeepgramSTTClient)
        client._user = self.user
        client._session_id = "room-1"
        client._audio_bytes_sent = 240_000  # ~60s at the estimated bitrate
        client._deduct_stt_usage()
        self.assertBilled(
            service=ServiceType.DEEPGRAM_STT,
            feature=FeatureType.VOICE_ROOM,
            min_cost_usd=Decimal("0.0001"),
        )

    def test_chat_stt_deduction_records(self):
        from llm.transcription import _deduct_stt_usage

        _deduct_stt_usage(self.user, audio_seconds=60.0)
        self.assertBilled(
            service=ServiceType.DEEPGRAM_STT,
            feature=FeatureType.CHAT,
            min_cost_usd=Decimal("0.0001"),
        )


class TestVideoGenerationBilling(BillingCoverageBase):
    """Matrix row #23 — `_record_video_billing` writes one row."""

    def test_record_video_billing_writes_row(self):
        from llm.video_tools import _record_video_billing

        class _Cfg:
            canonical_id = "sora/sora-1"

        async_to_sync(_record_video_billing)(
            context={
                "user_id": str(self.user.id),
                "conversation_id": "conv-1",
            },
            cost_usd=Decimal("0.10"),
            model_config=_Cfg(),
            duration_seconds=5.0,
        )
        self.assertBilled(
            service=ServiceType.VIDEO_GENERATION,
            feature=FeatureType.CHAT,
            min_cost_usd=Decimal("0.10"),
        )
        row = UsageLog.objects.filter(
            user=self.user, service=ServiceType.VIDEO_GENERATION,
        ).first()
        self.assertEqual(row.model_id, "sora/sora-1")

    def test_video_billing_skipped_without_user(self):
        from llm.video_tools import _record_video_billing

        class _Cfg:
            canonical_id = "sora/sora-1"

        async_to_sync(_record_video_billing)(
            context={"user_id": None},
            cost_usd=Decimal("0.10"),
            model_config=_Cfg(),
            duration_seconds=5.0,
        )
        self.assertNotBilled(service=ServiceType.VIDEO_GENERATION)


class TestBraveSearchBilling(BillingCoverageBase):
    """Matrix row #18 — the `/api/quota/deduct/` call the brave-search
    sidecar makes after a successful search writes one BRAVE_SEARCH row."""

    def test_quota_deduct_endpoint_bills_brave_search(self):
        from rest_framework.test import APIClient

        client = APIClient()
        client.force_authenticate(user=self.user)
        response = client.post(
            "/api/quota/deduct/",
            {"service": "brave_search", "request_count": 1,
             "feature": "search"},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertBilled(
            service=ServiceType.BRAVE_SEARCH,
            feature=FeatureType.SEARCH,
            min_cost_usd=Decimal("0.004"),
        )


class TestGoogleMapsPhotoProxy(BillingCoverageBase):
    """Matrix row #19b — the frontend place-photo proxy requires auth,
    validates its payload and meters usage."""

    URL = "/api/llm/google-maps/places/search-photo/"

    def _authed_client(self):
        from rest_framework.test import APIClient

        client = APIClient()
        client.force_authenticate(user=self.user)
        return client

    @staticmethod
    def _mock_upstream(mock_client_cls, status_code=200, body=None):
        from unittest.mock import MagicMock

        mock_response = MagicMock()
        mock_response.status_code = status_code
        mock_response.json.return_value = body or {
            "success": True, "photo_url": "https://example.test/p.jpg",
        }
        (mock_client_cls.return_value.__enter__
         .return_value.post.return_value) = mock_response
        return mock_response

    def test_requires_authentication(self):
        from rest_framework.test import APIClient

        response = APIClient().post(
            self.URL, {"query": "Eiffel Tower"}, format="json",
        )
        self.assertIn(response.status_code, (401, 403))
        self.assertNotBilled(service=ServiceType.GOOGLE_MAPS)

    def test_rejects_invalid_payload(self):
        client = self._authed_client()
        self.assertEqual(
            client.post(self.URL, {"query": ""}, format="json").status_code,
            400,
        )
        self.assertEqual(
            client.post(
                self.URL,
                {"query": "x", "latitude": 200},
                format="json",
            ).status_code,
            400,
        )
        self.assertNotBilled(service=ServiceType.GOOGLE_MAPS)

    def test_success_records_usage_for_request_user(self):
        client = self._authed_client()
        with patch("llm.services.google_maps_photo_service.httpx_sync.Client") as mock_client_cls:
            self._mock_upstream(mock_client_cls)
            response = client.post(
                self.URL,
                {"query": "Eiffel Tower", "latitude": 48.858,
                 "longitude": 2.294, "max_width": 400},
                format="json",
            )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertBilled(
            service=ServiceType.GOOGLE_MAPS,
            feature=FeatureType.CHAT,
        )
        row = UsageLog.objects.filter(
            user=self.user, service=ServiceType.GOOGLE_MAPS,
        ).first()
        self.assertEqual(row.model_id, "places_photo")

    def test_upstream_failure_does_not_bill(self):
        client = self._authed_client()
        with patch("llm.services.google_maps_photo_service.httpx_sync.Client") as mock_client_cls:
            self._mock_upstream(
                mock_client_cls,
                body={"success": False, "error": "no photo"},
            )
            response = client.post(
                self.URL, {"query": "Nowhere"}, format="json",
            )
        self.assertEqual(response.status_code, 200)
        self.assertNotBilled(service=ServiceType.GOOGLE_MAPS)


class TestConnectionEndpointSecurity(BillingCoverageBase):
    """test-connection dispatches a real completion — must be
    authenticated and rate-limited (stolen-key validation oracle)."""

    URL = "/api/llm/models/test-connection/"

    def test_requires_authentication(self):
        from rest_framework.test import APIClient

        response = APIClient().post(
            self.URL, {"api_key": "sk-or-x"}, format="json",
        )
        self.assertIn(response.status_code, (401, 403))

    def test_rate_limited_after_ten_requests(self):
        from django.core.cache import cache as dj_cache

        from rest_framework.test import APIClient

        client = APIClient()
        client.force_authenticate(user=self.user)

        dj_cache.clear()
        try:
            with patch(
                "django_ratelimit.core._get_window",
                return_value=1_999_999_999,
            ), patch("llm.views.model_catalog.OpenRouterClient") as mock_client_cls:
                mock_client_cls.return_value.complete.return_value = {}
                mock_client_cls.return_value.list_models.return_value = []
                for i in range(10):
                    response = client.post(
                        self.URL, {"api_key": "sk-or-x"}, format="json",
                    )
                    self.assertEqual(
                        response.status_code, 200,
                        f"request {i} unexpectedly blocked: {response.content}",
                    )
                blocked = client.post(
                    self.URL, {"api_key": "sk-or-x"}, format="json",
                )
                # Ratelimited subclasses PermissionDenied → DRF renders 403.
                self.assertEqual(blocked.status_code, 403)
        finally:
            dj_cache.clear()


class TestStreamCompleteRateLimitError(BillingCoverageBase):
    """F821 regression — the SSE rate-limit error generator must not
    reference an out-of-scope exception variable."""

    def test_rate_limit_error_yields_sse_without_nameerror(self):
        from rest_framework.test import APIClient

        client = APIClient()
        client.force_authenticate(user=self.user)
        with patch("llm.views.completions.RateLimiter") as mock_rl:
            mock_rl.return_value.wait_if_needed.side_effect = Exception(
                "rate limited",
            )
            response = client.post(
                "/api/llm/completions/stream-complete/",
                {
                    "model": "openai/gpt-4o-mini",
                    "messages": [{"role": "user", "content": "hi"}],
                },
                format="json",
            )
        self.assertEqual(response.status_code, 429)
        body = b"".join(response.streaming_content)
        self.assertIn(b"event: error", body)
