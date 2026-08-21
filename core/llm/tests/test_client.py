"""
Tests for OpenRouter client.
"""

import requests
from decimal import Decimal
from unittest.mock import patch, MagicMock

from django.test import TestCase, override_settings

from ..client import OpenRouterClient
from ..exceptions import OpenRouterException, RateLimitException


class TestOpenRouterClient(TestCase):
    """Test cases for OpenRouter client."""

    def setUp(self):
        """Set up test client."""
        self.client = OpenRouterClient(api_key="test_key")

    @patch("llm.client.requests.Session")
    def test_client_initialization(self, mock_session):
        """Test client initializes with proper headers."""
        client = OpenRouterClient(api_key="test_api_key")

        self.assertEqual(client.api_key, "test_api_key")
        self.assertEqual(client.base_url, "https://openrouter.ai/api/v1")

    def test_client_requires_api_key(self):
        """Test client raises error without API key."""
        # The client resolves keys via the APIKeyResolver singleton, which
        # reads settings.OPENROUTER_API_KEY at first use — clear all three
        # sources (settings, env, cached singleton) to hit the error path.
        with override_settings(OPENROUTER_API_KEY=""), \
             patch.dict("os.environ", {}, clear=True), \
             patch("llm.services.api_key_resolver._resolver", None):
            with self.assertRaises(ValueError) as context:
                OpenRouterClient()

            self.assertIn("API key", str(context.exception))

    @patch.object(OpenRouterClient, "_make_request")
    def test_list_models(self, mock_request):
        """Test listing available models."""
        mock_models = {
            "data": [
                {"id": "openai/gpt-4", "name": "GPT-4"},
                {"id": "anthropic/claude-3-opus", "name": "Claude 3 Opus"},
            ]
        }
        mock_request.return_value = mock_models

        models = self.client.list_models()

        self.assertEqual(len(models), 2)
        self.assertEqual(models[0]["id"], "openai/gpt-4")
        mock_request.assert_called_once_with("GET", "/models")

    @patch.object(OpenRouterClient, "_make_request")
    def test_complete(self, mock_request):
        """Test completion generation."""
        mock_response = {
            "choices": [{"message": {"content": "Test response"}}],
            "model": "openai/gpt-3.5-turbo",
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        }
        mock_request.return_value = mock_response

        with patch.object(
            self.client,
            "_calculate_cost",
            return_value={
                "prompt_cost": Decimal("0.0006"),
                "completion_cost": Decimal("0.0004"),
                "total_cost": Decimal("0.001"),
            },
        ):
            result = self.client.complete(
                model="openai/gpt-3.5-turbo",
                messages=[{"role": "user", "content": "Hello"}],
            )

        self.assertEqual(result["content"], "Test response")
        self.assertEqual(result["model"], "openai/gpt-3.5-turbo")
        self.assertEqual(result["usage"]["total_tokens"], 15)
        self.assertEqual(result["cost"], Decimal("0.001"))
        self.assertEqual(result["prompt_cost"], Decimal("0.0006"))
        self.assertEqual(result["completion_cost"], Decimal("0.0004"))

    @patch.object(OpenRouterClient, "_make_request")
    def test_complete_with_fallback(self, mock_request):
        """Test completion with automatic fallback."""
        # First model fails, second succeeds
        mock_request.side_effect = [
            OpenRouterException("Model unavailable"),
            {
                "choices": [{"message": {"content": "Success"}}],
                "model": "openai/gpt-3.5-turbo",
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 5,
                    "total_tokens": 15,
                },
            },
        ]

        with patch.object(self.client, "check_model_availability", return_value=True):
            with patch.object(
                self.client,
                "_calculate_cost",
                return_value={
                    "prompt_cost": Decimal("0.0006"),
                    "completion_cost": Decimal("0.0004"),
                    "total_cost": Decimal("0.001"),
                },
            ):
                result = self.client.complete_with_fallback(
                    models=["openai/gpt-4", "openai/gpt-3.5-turbo"],
                    messages=[{"role": "user", "content": "Hello"}],
                )

        self.assertEqual(result["content"], "Success")
        self.assertEqual(result["model_used"], "openai/gpt-3.5-turbo")
        self.assertEqual(result["fallback_attempts"], 1)

    def test_complete_with_fallback_all_fail(self):
        """Test fallback raises exception when all models fail."""
        with patch.object(self.client, "check_model_availability", return_value=False):
            with self.assertRaises(OpenRouterException) as context:
                self.client.complete_with_fallback(
                    models=["openai/gpt-4", "openai/gpt-3.5-turbo"],
                    messages=[{"role": "user", "content": "Hello"}],
                )

            self.assertIn("All models failed", str(context.exception))

    @patch("llm.client.requests.Session.request")
    def test_retry_logic(self, mock_request):
        """Test automatic retry with exponential backoff."""
        # First two attempts fail, third succeeds
        mock_response_fail = MagicMock()
        mock_response_fail.status_code = 500
        mock_response_fail.raise_for_status.side_effect = requests.exceptions.HTTPError(
            "Server error"
        )

        mock_response_success = MagicMock()
        mock_response_success.status_code = 200
        mock_response_success.json.return_value = {"success": True}

        mock_request.side_effect = [
            mock_response_fail,
            mock_response_fail,
            mock_response_success,
        ]

        with patch("time.sleep"):  # Mock sleep to speed up test
            result = self.client._make_request("GET", "/test")

        self.assertEqual(result, {"success": True})
        self.assertEqual(mock_request.call_count, 3)

    @patch("llm.client.requests.Session.request")
    def test_rate_limit_handling(self, mock_request):
        """Test rate limit handling with retry."""
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.headers = {"Retry-After": "1"}
        mock_request.return_value = mock_response

        with patch("time.sleep"):  # Mock sleep to speed up test
            with self.assertRaises(RateLimitException):
                self.client._make_request("GET", "/test")
