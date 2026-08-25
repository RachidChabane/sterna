"""
Tests for LLM API endpoints.
"""

from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.utils import timezone
from rest_framework.test import APITestCase
from rest_framework import status

from ..models import ModelCatalog

User = get_user_model()


class TestModelCatalogAPI(APITestCase):
    """Test cases for model catalog API endpoints."""

    def setUp(self):
        """Set up test user and authentication."""
        self.user = User.objects.create_user(
            email="test@example.com", password="testpass123"
        )
        self.client.force_authenticate(user=self.user)
        # The list endpoint caches responses for 5 minutes — clear between tests
        cache.clear()

    def test_list_models(self):
        """Test listing available models."""
        # Create test models (fetched_at set so the catalog isn't considered stale)
        ModelCatalog.objects.create(
            model_id="openai/gpt-4",
            name="GPT-4",
            provider="openai",
            is_available=True,
            fetched_at=timezone.now(),
        )
        ModelCatalog.objects.create(
            model_id="anthropic/claude-3",
            name="Claude 3",
            provider="anthropic",
            is_available=True,
            fetched_at=timezone.now(),
        )

        response = self.client.get("/api/llm/models/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data["results"]
        # The virtual Sterna Auto entry is prepended on unfiltered page 1
        self.assertEqual(results[0]["model_id"], "ornithops/sterna")
        model_ids = {m["model_id"] for m in results}
        self.assertIn("openai/gpt-4", model_ids)
        self.assertIn("anthropic/claude-3", model_ids)
        self.assertEqual(response.data["count"], 3)

    def test_list_models_with_filters(self):
        """Test listing models with filters."""
        ModelCatalog.objects.create(
            model_id="openai/gpt-4",
            name="GPT-4",
            provider="openai",
            is_available=True,
            supports_functions=True,
            fetched_at=timezone.now(),
        )
        ModelCatalog.objects.create(
            model_id="anthropic/claude-3",
            name="Claude 3",
            provider="anthropic",
            is_available=True,
            supports_functions=False,
            fetched_at=timezone.now(),
        )

        # Filter by provider (no Sterna Auto entry when a provider filter is active)
        response = self.client.get("/api/llm/models/", {"provider": "openai"})
        results = response.data["results"]
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["provider"], "openai")

        # Filter by capabilities (Sterna Auto is still prepended on page 1)
        response = self.client.get("/api/llm/models/", {"supports_functions": "true"})
        model_ids = [m["model_id"] for m in response.data["results"]]
        self.assertIn("openai/gpt-4", model_ids)
        self.assertNotIn("anthropic/claude-3", model_ids)

    @patch("llm.views.CatalogService")
    def test_check_model_availability(self, mock_catalog_service):
        """Test checking model availability endpoint."""
        mock_service = mock_catalog_service.return_value
        mock_service.check_model_availability.return_value = True

        response = self.client.post(
            "/api/llm/models/check_availability/", {"model_id": "openai/gpt-4"}
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["is_available"])
        self.assertEqual(response.data["model_id"], "openai/gpt-4")

    @patch("llm.views.CatalogService")
    def test_refresh_catalog(self, mock_catalog_service):
        """Test refreshing model catalog."""
        mock_service = mock_catalog_service.return_value
        mock_service.refresh_catalog.return_value = {
            "success": True,
            "total_models": 10,
            "providers": {"openai": 5, "anthropic": 5},
            "timestamp": timezone.now().isoformat(),
        }

        response = self.client.post("/api/llm/models/refresh/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["success"])
        self.assertEqual(response.data["total_models"], 10)

    @patch("llm.views.CatalogService")
    def test_get_model_tiers(self, mock_catalog_service):
        """Test getting model tiers."""
        mock_service = mock_catalog_service.return_value
        mock_service.get_models_by_tier.return_value = ["openai/gpt-3.5-turbo"]

        response = self.client.get("/api/llm/models/tiers/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 3)  # budget, balanced, quality

        # Check structure
        tier_data = response.data[0]
        self.assertIn("tier", tier_data)
        self.assertIn("models", tier_data)
        self.assertIn("cost_estimate", tier_data)
        self.assertIn("available_count", tier_data)


class TestCompletionAPI(APITestCase):
    """Test cases for completion API endpoints."""

    def setUp(self):
        """Set up test user and authentication."""
        self.user = User.objects.create_user(
            email="test@example.com", password="testpass123"
        )
        self.client.force_authenticate(user=self.user)

    @patch("llm.views.OpenRouterClient")
    @patch("llm.views.RateLimiter")
    def test_complete(self, mock_rate_limiter, mock_client_class):
        """Test single model completion."""
        mock_client = mock_client_class.return_value
        mock_client.complete.return_value = {
            "content": "Test response",
            "model": "openai/gpt-3.5-turbo",
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            "cost": Decimal("0.001"),
            "prompt_cost": Decimal("0.0006"),
            "completion_cost": Decimal("0.0004"),
        }

        mock_limiter = mock_rate_limiter.return_value
        mock_limiter.wait_if_needed.return_value = None

        response = self.client.post(
            "/api/llm/completions/complete/",
            {
                "model": "openai/gpt-3.5-turbo",
                "messages": [{"role": "user", "content": "Hello"}],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["content"], "Test response")
        self.assertEqual(response.data["model"], "openai/gpt-3.5-turbo")

    @patch("llm.views.OpenRouterClient")
    def test_complete_with_fallback(self, mock_client_class):
        """Test completion with fallback models."""
        mock_client = mock_client_class.return_value
        mock_client.complete_with_fallback.return_value = {
            "content": "Fallback response",
            "model": "openai/gpt-3.5-turbo",
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            "cost": Decimal("0.001"),
            "prompt_cost": Decimal("0.0006"),
            "completion_cost": Decimal("0.0004"),
            "model_used": "openai/gpt-3.5-turbo",
            "fallback_attempts": 1,
        }

        response = self.client.post(
            "/api/llm/completions/complete_with_fallback/",
            {
                "models": ["openai/gpt-4", "openai/gpt-3.5-turbo"],
                "messages": [{"role": "user", "content": "Hello"}],
                "max_cost": 0.1,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["content"], "Fallback response")
        self.assertEqual(response.data["model_used"], "openai/gpt-3.5-turbo")
        self.assertEqual(response.data["fallback_attempts"], 1)

    @patch("llm.views.CatalogService")
    def test_estimate_cost(self, mock_catalog_service):
        """Test cost estimation endpoint."""
        mock_service = mock_catalog_service.return_value
        mock_service.estimate_cost.return_value = Decimal("0.045")
        mock_service.get_model_pricing.return_value = {
            "prompt_price": 0.03,
            "completion_price": 0.06,
        }

        response = self.client.post(
            "/api/llm/completions/estimate_cost/",
            {
                "model_id": "openai/gpt-4",
                "prompt_tokens": 1000,
                "completion_tokens": 500,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(float(response.data["total_cost"]), 0.045)
        self.assertEqual(response.data["currency"], "USD")

    @patch("llm.views.RateLimiter")
    def test_rate_limit_info(self, mock_rate_limiter):
        """Test getting rate limit information."""
        mock_limiter = mock_rate_limiter.return_value
        mock_limiter.get_limits_info.return_value = {
            "model_id": "openai/gpt-4",
            "rate_per_second": 20,
            "burst_capacity": 5,
            "current_tokens": 3.5,
            "tokens_available": True,
            "time_until_available": 0,
        }

        response = self.client.get(
            "/api/llm/completions/rate_limit_info/", {"model_id": "openai/gpt-4"}
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["model_id"], "openai/gpt-4")
        self.assertEqual(response.data["rate_per_second"], 20)
        self.assertTrue(response.data["tokens_available"])

    @patch("llm.views.CatalogService")
    def test_estimate_batch_cost_builds_prompt_through_prompts_v2(self, mock_catalog_service):
        """Both the global and per-model system prompts route through the
        prompts_v2 builder, exercising the same code path the LangChain
        agent uses in production; the per-model prompt has every feature
        flag on.

        Pins the prompt source: it spies on OptimizedPromptBuilder.build_full_prompt
        (delegating to the real implementation) and asserts prompts_v2-distinctive
        markers are present in what it actually built -- the toggleable_capabilities
        section (STATIC_CORE_PROMPTS, present in both prompts) plus, in the
        per-model prompt, one CONDITIONAL_PROMPTS notice per enabled feature flag."""
        from ..prompts_v2.optimized_builder import OptimizedPromptBuilder

        capabilities_marker = "## Available Capabilities"
        feature_markers = {
            "mcp_tools": "[CONNECTORS ENABLED]",
            "reasoning": "[REASONING ENABLED]",
            "file_tools": "[FILE TOOLS ENABLED]",
            "image_generation": "[IMAGE GENERATION & EDITING ENABLED]",
            "video_generation": "[VIDEO GENERATION ENABLED]",
        }
        captured_prompts = []
        real_build_full_prompt = OptimizedPromptBuilder.build_full_prompt

        def _capturing_build_full_prompt(self, *args, **kwargs):
            prompt_text, metadata = real_build_full_prompt(self, *args, **kwargs)
            captured_prompts.append(prompt_text)
            return prompt_text, metadata

        mock_catalog = mock_catalog_service.return_value
        mock_catalog.get_model.return_value = {
            "name": "GPT-4",
            "max_tokens": 8192,
            "max_completion_tokens": 2048,
        }
        mock_catalog.estimate_cost.return_value = Decimal("0.01")

        with patch.object(
            OptimizedPromptBuilder, "build_full_prompt", _capturing_build_full_prompt
        ):
            response = self.client.post(
                "/api/llm/completions/estimate-batch-cost/",
                {
                    "model_ids": ["openai/gpt-4"],
                    "typed_text": "Summarize this document for me.",
                    "system_prompt": "You are a helpful assistant.",
                    "enable_mcp_tools": True,
                    "features_by_model": {
                        "openai/gpt-4": {
                            "enable_mcp_tools": True,
                            "enable_reasoning": True,
                            "enable_file_tools": True,
                            "enable_image_generation": True,
                            "enable_video_generation": True,
                            "system_prompt": "Custom per-model instructions.",
                        }
                    },
                },
                format="json",
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["costs"]), 1)
        self.assertEqual(response.data["costs"][0]["model_id"], "openai/gpt-4")
        self.assertGreater(response.data["prompt_tokens"], 0)

        # Pin the prompt source: build_full_prompt (the prompts_v2 API) must
        # actually have been called -- once for the global estimate, once for
        # the per-model override -- and every prompt it built must carry the
        # shared capabilities marker.
        self.assertEqual(len(captured_prompts), 2)
        global_prompt, per_model_prompt = captured_prompts
        for prompt_text in captured_prompts:
            self.assertIn(capabilities_marker, prompt_text)

        # The global estimate only had enable_mcp_tools set.
        self.assertIn(feature_markers["mcp_tools"], global_prompt)

        # The per-model estimate had every feature flag set -- each must
        # have produced its own distinctive CONDITIONAL_PROMPTS notice.
        for marker in feature_markers.values():
            self.assertIn(marker, per_model_prompt)
