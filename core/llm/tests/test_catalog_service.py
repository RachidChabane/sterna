"""
Tests for catalog service.
"""

from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.test import TransactionTestCase
from django.core.cache import cache

from ..client import OpenRouterClient
from ..catalog_service import CatalogService, _detect_capabilities
from ..models import ModelCatalog


class TestDetectCapabilities(TransactionTestCase):
    """Test cases for _detect_capabilities helper function."""

    def setUp(self):
        """Stub the provider lookup so tests never hit network/Redis."""
        patcher = patch(
            'llm.catalog_service.supports_stream_cancellation',
            side_effect=lambda provider: provider in ('openai', 'anthropic', 'azure'),
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_detect_streaming_only(self):
        """Streaming is universal — OpenRouter supports it for all models."""
        capabilities = _detect_capabilities(['stream', 'temperature', 'max_tokens'], {})
        self.assertTrue(capabilities['streaming'])
        self.assertFalse(capabilities['functions'])

    def test_detect_functions_only(self):
        """Test detection of function calling support."""
        capabilities = _detect_capabilities(['tools', 'temperature'], {})
        self.assertTrue(capabilities['streaming'])  # streaming is universal
        self.assertTrue(capabilities['functions'])

    def test_detect_both_capabilities(self):
        """Test detection of both streaming and functions."""
        capabilities = _detect_capabilities(['stream', 'tools', 'tool_choice'], {})
        self.assertTrue(capabilities['streaming'])
        self.assertTrue(capabilities['functions'])

    def test_detect_no_capabilities(self):
        """Test detection with no special capabilities."""
        capabilities = _detect_capabilities(['temperature', 'max_tokens', 'top_p'], {})
        self.assertTrue(capabilities['streaming'])  # streaming is universal
        self.assertFalse(capabilities['functions'])

    def test_detect_empty_list(self):
        """Test detection with empty list."""
        capabilities = _detect_capabilities([], {})
        self.assertTrue(capabilities['streaming'])  # streaming is universal
        self.assertFalse(capabilities['functions'])

    def test_detect_none_value(self):
        """Test detection with None value."""
        capabilities = _detect_capabilities(None, {})
        self.assertTrue(capabilities['streaming'])  # streaming is universal
        self.assertFalse(capabilities['functions'])

    def test_detect_case_insensitive(self):
        """Test that detection is case-insensitive."""
        capabilities = _detect_capabilities(['STREAM', 'TOOLS'], {})
        self.assertTrue(capabilities['streaming'])
        self.assertTrue(capabilities['functions'])

    def test_detect_parallel_tool_calls(self):
        """Test detection with parallel_tool_calls parameter."""
        capabilities = _detect_capabilities(['parallel_tool_calls'], {})
        self.assertTrue(capabilities['functions'])

    def test_detect_legacy_functions(self):
        """Test detection with legacy 'functions' parameter."""
        capabilities = _detect_capabilities(['functions'], {})
        self.assertTrue(capabilities['functions'])

    def test_detect_structured_outputs(self):
        """Test detection of structured outputs support."""
        capabilities = _detect_capabilities(['structured_outputs', 'temperature'], {})
        self.assertFalse(capabilities['functions'])
        self.assertTrue(capabilities['structured_outputs'])
        self.assertFalse(capabilities['reasoning'])

    def test_detect_reasoning(self):
        """Test detection of reasoning support."""
        capabilities = _detect_capabilities(['reasoning', 'temperature'], {})
        self.assertFalse(capabilities['functions'])
        self.assertFalse(capabilities['structured_outputs'])
        self.assertTrue(capabilities['reasoning'])

    def test_detect_include_reasoning(self):
        """Test detection with include_reasoning parameter."""
        capabilities = _detect_capabilities(['include_reasoning'], {})
        self.assertFalse(capabilities['functions'])
        self.assertFalse(capabilities['structured_outputs'])
        self.assertTrue(capabilities['reasoning'])

    def test_detect_all_capabilities(self):
        """Test detection with all capabilities."""
        capabilities = _detect_capabilities(
            ['stream', 'tools', 'structured_outputs', 'reasoning'], {}
        )
        self.assertTrue(capabilities['streaming'])
        self.assertTrue(capabilities['functions'])
        self.assertTrue(capabilities['structured_outputs'])
        self.assertTrue(capabilities['reasoning'])

    def test_detect_prompt_caching_from_pricing(self):
        """Prompt caching is detected via cache pricing fields."""
        capabilities = _detect_capabilities(
            ['tools'], {'prompt': '0.000003', 'input_cache_read': '0.0000001'}
        )
        self.assertTrue(capabilities['prompt_caching'])

        capabilities = _detect_capabilities(['tools'], {'prompt': '0.000003'})
        self.assertFalse(capabilities['prompt_caching'])

    @patch('llm.catalog_service.supports_stream_cancellation')
    def test_detect_stream_cancellation_supported_provider(self, mock_supports):
        """Test stream cancellation detection for supported providers."""
        # Mock to return True for supported providers
        mock_supports.return_value = True

        # OpenAI supports stream cancellation
        capabilities = _detect_capabilities(['temperature'], {}, 'openai')
        self.assertTrue(capabilities['stream_cancellation'])

        # Anthropic supports stream cancellation
        capabilities = _detect_capabilities(['temperature'], {}, 'anthropic')
        self.assertTrue(capabilities['stream_cancellation'])

        # Azure supports stream cancellation
        capabilities = _detect_capabilities(['temperature'], {}, 'azure')
        self.assertTrue(capabilities['stream_cancellation'])

    @patch('llm.catalog_service.supports_stream_cancellation')
    def test_detect_stream_cancellation_unsupported_provider(self, mock_supports):
        """Test stream cancellation detection for unsupported providers."""
        # Mock to return False for unsupported providers
        mock_supports.return_value = False

        # Google does not support stream cancellation
        capabilities = _detect_capabilities(['temperature'], {}, 'google')
        self.assertFalse(capabilities['stream_cancellation'])

        # Groq does not support stream cancellation
        capabilities = _detect_capabilities(['temperature'], {}, 'groq')
        self.assertFalse(capabilities['stream_cancellation'])

        # Mistral does not support stream cancellation
        capabilities = _detect_capabilities(['temperature'], {}, 'mistral')
        self.assertFalse(capabilities['stream_cancellation'])

    @patch('llm.catalog_service.supports_stream_cancellation')
    def test_detect_stream_cancellation_case_insensitive(self, mock_supports):
        """Test that provider names are case-insensitive."""
        # Mock to return True (the service itself handles case insensitivity)
        mock_supports.return_value = True

        # Test uppercase
        capabilities = _detect_capabilities(['temperature'], {}, 'OPENAI')
        self.assertTrue(capabilities['stream_cancellation'])

        # Test mixed case
        capabilities = _detect_capabilities(['temperature'], {}, 'OpenAI')
        self.assertTrue(capabilities['stream_cancellation'])

    @patch('llm.catalog_service.supports_stream_cancellation')
    def test_detect_stream_cancellation_empty_provider(self, mock_supports):
        """Test stream cancellation with empty or unknown provider."""
        # Mock to return False for empty/unknown
        mock_supports.return_value = False

        # Empty provider
        capabilities = _detect_capabilities(['temperature'], {}, '')
        self.assertFalse(capabilities['stream_cancellation'])

        # Unknown provider
        capabilities = _detect_capabilities(['temperature'], {}, 'unknown')
        self.assertFalse(capabilities['stream_cancellation'])


class TestCatalogService(TransactionTestCase):
    """Test cases for catalog service.

    Mock model data must pass `_meets_minimum_requirements`: tool support,
    context window >= 32768, image input modality, and no image/audio/:free
    marker in the model ID — models failing any of these are filtered out.
    """

    def setUp(self):
        """Set up test service."""
        self.mock_client = MagicMock(spec=OpenRouterClient)
        self.service = CatalogService(client=self.mock_client)
        cache.clear()
        # Stub the provider lookup so tests never hit network/Redis
        patcher = patch(
            'llm.catalog_service.supports_stream_cancellation',
            side_effect=lambda provider: provider in ('openai', 'anthropic', 'azure'),
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_fetch_and_cache_models(self):
        """Test fetching and caching model catalog with complete data."""
        mock_models = [
            {
                "id": "openai/gpt-4",
                "name": "GPT-4",
                "pricing": {"prompt": "0.00003", "completion": "0.00006"},  # Per token
                "context_length": 128000,
                "status": "available",
                "supported_parameters": ["stream", "tools", "tool_choice", "structured_outputs", "temperature"],
                "architecture": {
                    "modality": "text+image->text",
                    "input_modalities": ["text", "image"],
                    "output_modalities": ["text"],
                    "tokenizer": "GPT-4",
                    "instruct_type": None
                },
                "top_provider": {
                    "context_length": 128000,
                    "max_completion_tokens": 4096,
                    "is_moderated": True
                },
                "default_parameters": {
                    "temperature": 0.7,
                    "top_p": 0.9
                }
            }
        ]
        self.mock_client.list_models.return_value = mock_models

        models = self.service.fetch_and_cache_models()

        self.assertEqual(len(models), 1)
        self.assertEqual(models[0]["id"], "openai/gpt-4")

        # Check database
        db_model = ModelCatalog.objects.get(model_id="openai/gpt-4")
        self.assertEqual(db_model.name, "GPT-4")
        self.assertEqual(db_model.provider, "openai")
        self.assertTrue(db_model.is_available)

        # Check capabilities are correctly detected
        self.assertTrue(db_model.supports_streaming)
        self.assertTrue(db_model.supports_functions)
        self.assertTrue(db_model.supports_structured_outputs)
        self.assertFalse(db_model.supports_reasoning)
        # OpenAI supports stream cancellation
        self.assertTrue(db_model.supports_stream_cancellation)

        # Check architecture details
        self.assertEqual(db_model.modality, "text+image->text")
        self.assertEqual(db_model.input_modalities, ["text", "image"])
        self.assertEqual(db_model.output_modalities, ["text"])
        self.assertEqual(db_model.tokenizer, "GPT-4")

        # Check top_provider details
        self.assertEqual(db_model.max_completion_tokens, 4096)
        self.assertTrue(db_model.is_moderated)

        # Check default_parameters
        self.assertEqual(db_model.default_parameters["temperature"], 0.7)
        self.assertEqual(db_model.default_parameters["top_p"], 0.9)

        # Check cache
        cached_models = cache.get(self.service.CACHE_KEY_ALL_MODELS)
        self.assertIsNotNone(cached_models)
        self.assertEqual(len(cached_models), 1)

    def test_check_model_availability(self):
        """Test checking model availability."""
        # Create model in database
        ModelCatalog.objects.create(
            model_id="openai/gpt-4", name="GPT-4", provider="openai", is_available=True
        )

        is_available = self.service.check_model_availability("openai/gpt-4")
        self.assertTrue(is_available)

        is_available = self.service.check_model_availability("nonexistent/model")
        self.assertFalse(is_available)

    def test_get_model_pricing(self):
        """Test getting model pricing information."""
        ModelCatalog.objects.create(
            model_id="openai/gpt-4",
            name="GPT-4",
            provider="openai",
            prompt_price=Decimal("0.03"),
            completion_price=Decimal("0.06"),
        )

        pricing = self.service.get_model_pricing("openai/gpt-4")

        self.assertEqual(pricing["prompt_price"], 0.03)
        self.assertEqual(pricing["completion_price"], 0.06)

    def test_estimate_cost(self):
        """Test cost estimation."""
        ModelCatalog.objects.create(
            model_id="openai/gpt-4",
            name="GPT-4",
            provider="openai",
            prompt_price=Decimal("0.03"),  # Per 1k tokens
            completion_price=Decimal("0.06"),  # Per 1k tokens
        )

        cost = self.service.estimate_cost("openai/gpt-4", 1000, 500)

        expected_cost = Decimal("0.03") + Decimal("0.03")  # 0.03 + 0.03
        self.assertEqual(cost, expected_cost)

    def test_get_models_by_tier(self):
        """Test getting models by tier."""
        # Create test models
        ModelCatalog.objects.create(
            model_id="openai/gpt-3.5-turbo",
            name="GPT-3.5 Turbo",
            provider="openai",
            is_available=True,
        )

        models = self.service.get_models_by_tier("budget")

        self.assertIn("openai/gpt-3.5-turbo", models)

    def test_refresh_catalog(self):
        """Test force refresh of catalog."""
        mock_models = [
            {
                "id": "openai/gpt-4",
                "name": "GPT-4",
                "status": "available",
                "context_length": 128000,
                "supported_parameters": ["stream", "tools"],
                "architecture": {"input_modalities": ["text", "image"]},
            },
            {
                "id": "anthropic/claude-3",
                "name": "Claude 3",
                "status": "available",
                "context_length": 200000,
                "supported_parameters": ["stream", "tools"],
                "architecture": {"input_modalities": ["text", "image"]},
            },
        ]
        self.mock_client.list_models.return_value = mock_models

        result = self.service.refresh_catalog()

        self.assertTrue(result["success"])
        self.assertEqual(result["total_models"], 2)
        self.assertIn("openai", result["providers"])

    def test_model_without_supported_parameters(self):
        """Models without supported_parameters are filtered out (no tool support)."""
        mock_models = [
            {
                "id": "test/model-basic",
                "name": "Test Model",
                "status": "available",
                "context_length": 128000,
                "architecture": {"input_modalities": ["text", "image"]},
                # No supported_parameters field
            }
        ]
        self.mock_client.list_models.return_value = mock_models

        models = self.service.fetch_and_cache_models()

        # Should not crash — model is filtered out of the catalog
        self.assertEqual(models, [])
        self.assertFalse(
            ModelCatalog.objects.filter(model_id="test/model-basic").exists()
        )

    def test_model_with_empty_supported_parameters(self):
        """Models with empty supported_parameters are filtered out (no tool support)."""
        mock_models = [
            {
                "id": "test/model-empty",
                "name": "Test Model Empty",
                "status": "available",
                "context_length": 128000,
                "architecture": {"input_modalities": ["text", "image"]},
                "supported_parameters": [],
            }
        ]
        self.mock_client.list_models.return_value = mock_models

        models = self.service.fetch_and_cache_models()

        # Should handle empty list gracefully — model is filtered out
        self.assertEqual(models, [])
        self.assertFalse(
            ModelCatalog.objects.filter(model_id="test/model-empty").exists()
        )

    def test_multimodal_model_detection(self):
        """Test detection of multimodal model capabilities."""
        mock_models = [
            {
                "id": "google/gemini-2.5-flash",
                "name": "Gemini 2.5 Flash",
                "status": "available",
                "context_length": 1048576,
                "supported_parameters": ["stream", "tools", "temperature"],
                "architecture": {
                    "modality": "text+image->text+image",
                    "input_modalities": ["text", "image"],
                    "output_modalities": ["text", "image"],
                    "tokenizer": "Gemini",
                },
                "top_provider": {
                    "context_length": 1048576,
                    "max_completion_tokens": 8192,
                    "is_moderated": False
                }
            }
        ]
        self.mock_client.list_models.return_value = mock_models

        self.service.fetch_and_cache_models()

        # Check multimodal capabilities
        db_model = ModelCatalog.objects.get(model_id="google/gemini-2.5-flash")
        self.assertEqual(db_model.modality, "text+image->text+image")
        self.assertIn("text", db_model.input_modalities)
        self.assertIn("image", db_model.input_modalities)
        self.assertIn("text", db_model.output_modalities)
        self.assertIn("image", db_model.output_modalities)

    def test_reasoning_model_detection(self):
        """Test detection of reasoning model capabilities."""
        mock_models = [
            {
                "id": "nvidia/llama-3.3-nemotron",
                "name": "Llama Nemotron",
                "status": "available",
                "context_length": 131072,
                "supported_parameters": ["reasoning", "include_reasoning", "tools", "temperature"],
                "architecture": {"input_modalities": ["text", "image"]},
                "top_provider": {
                    "context_length": 131072,
                    "max_completion_tokens": None,
                    "is_moderated": False
                }
            }
        ]
        self.mock_client.list_models.return_value = mock_models

        self.service.fetch_and_cache_models()

        # Check reasoning capabilities
        db_model = ModelCatalog.objects.get(model_id="nvidia/llama-3.3-nemotron")
        self.assertTrue(db_model.supports_reasoning)
        self.assertTrue(db_model.supports_streaming)  # streaming is universal
        self.assertTrue(db_model.supports_functions)

    def test_stream_cancellation_by_provider(self):
        """Test that stream cancellation is correctly set based on provider."""
        base_model = {
            "status": "available",
            "context_length": 128000,
            "supported_parameters": ["tools", "temperature"],
            "architecture": {"input_modalities": ["text", "image"]},
        }
        mock_models = [
            # OpenAI model - supports stream cancellation
            {**base_model, "id": "openai/gpt-3.5-turbo", "name": "GPT-3.5 Turbo"},
            # Google model - does NOT support stream cancellation
            {**base_model, "id": "google/gemini-pro", "name": "Gemini Pro"},
            # Anthropic model - supports stream cancellation
            {**base_model, "id": "anthropic/claude-3-opus", "name": "Claude 3 Opus"},
        ]
        self.mock_client.list_models.return_value = mock_models

        self.service.fetch_and_cache_models()

        # Check OpenAI model
        openai_model = ModelCatalog.objects.get(model_id="openai/gpt-3.5-turbo")
        self.assertEqual(openai_model.provider, "openai")
        self.assertTrue(openai_model.supports_stream_cancellation)

        # Check Google model
        google_model = ModelCatalog.objects.get(model_id="google/gemini-pro")
        self.assertEqual(google_model.provider, "google")
        self.assertFalse(google_model.supports_stream_cancellation)

        # Check Anthropic model
        anthropic_model = ModelCatalog.objects.get(model_id="anthropic/claude-3-opus")
        self.assertEqual(anthropic_model.provider, "anthropic")
        self.assertTrue(anthropic_model.supports_stream_cancellation)
