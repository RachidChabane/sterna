"""
Tests for provider capabilities service.
"""

from unittest.mock import patch
from django.test import TestCase
from django.core.cache import cache

from ..provider_capabilities_service import (
    _normalize_provider_name,
    _map_provider_names_to_slugs,
    supports_stream_cancellation,
    get_stream_cancellation_providers,
    CACHE_KEY_STREAM_CANCELLATION,
)


class TestProviderCapabilitiesService(TestCase):
    """Test cases for provider capabilities service."""

    def setUp(self):
        """Clear cache before each test."""
        cache.clear()

    def test_normalize_provider_name(self):
        """Test provider name normalization."""
        self.assertEqual(_normalize_provider_name("OpenAI"), "openai")
        self.assertEqual(_normalize_provider_name("Google AI Studio"), "googleaistudio")
        self.assertEqual(_normalize_provider_name("AWS Bedrock"), "awsbedrock")
        self.assertEqual(_normalize_provider_name("xAI"), "xai")
        self.assertEqual(_normalize_provider_name("DeepInfra"), "deepinfra")

    def test_map_provider_names_to_slugs_direct_match(self):
        """Test direct matching of provider names to slugs."""
        doc_names = ["OpenAI", "Anthropic", "Google"]
        api_map = {
            "OpenAI": "openai",
            "Anthropic": "anthropic",
            "Google": "google",
        }

        slugs = _map_provider_names_to_slugs(doc_names, api_map)

        self.assertIn("openai", slugs)
        self.assertIn("anthropic", slugs)
        self.assertIn("google", slugs)
        self.assertEqual(len(slugs), 3)

    def test_map_provider_names_to_slugs_partial_match(self):
        """Test partial matching for complex provider names."""
        doc_names = ["Google AI Studio", "AWS Bedrock"]
        api_map = {
            "Google": "google",
            "Google AI Studio": "google-ai-studio",
            "Amazon Bedrock": "amazon-bedrock",
        }

        slugs = _map_provider_names_to_slugs(doc_names, api_map)

        # Should match both google slugs
        self.assertTrue("google" in slugs or "google-ai-studio" in slugs)
        # Should match amazon bedrock
        self.assertIn("amazon-bedrock", slugs)

    def test_map_provider_names_to_slugs_no_match(self):
        """Test handling of unmatched provider names."""
        doc_names = ["UnknownProvider"]
        api_map = {
            "OpenAI": "openai",
            "Anthropic": "anthropic",
        }

        # Should not crash, just log warning
        slugs = _map_provider_names_to_slugs(doc_names, api_map)

        # Should be empty or not include unknown provider
        self.assertNotIn("unknownprovider", slugs)

    @patch('llm.provider_capabilities_service._scrape_streaming_docs')
    @patch('llm.provider_capabilities_service._fetch_provider_slugs')
    def test_get_stream_cancellation_providers_caching(self, mock_fetch, mock_scrape):
        """Test that results are properly cached."""
        # Setup mocks
        mock_scrape.return_value = {
            "supported": ["OpenAI", "Anthropic"],
            "unsupported": ["Google"],
        }
        mock_fetch.return_value = {
            "OpenAI": "openai",
            "Anthropic": "anthropic",
            "Google": "google",
        }

        # First call - should hit API
        providers1 = get_stream_cancellation_providers()

        self.assertIn("openai", providers1)
        self.assertIn("anthropic", providers1)
        self.assertNotIn("google", providers1)

        # Verify mocks were called
        self.assertTrue(mock_scrape.called)
        self.assertTrue(mock_fetch.called)

        # Reset mocks
        mock_scrape.reset_mock()
        mock_fetch.reset_mock()

        # Second call - should use cache
        providers2 = get_stream_cancellation_providers()

        # Should return same data
        self.assertEqual(providers1, providers2)

        # Should NOT call APIs again
        self.assertFalse(mock_scrape.called)
        self.assertFalse(mock_fetch.called)

    @patch('llm.provider_capabilities_service._scrape_streaming_docs')
    @patch('llm.provider_capabilities_service._fetch_provider_slugs')
    def test_get_stream_cancellation_providers_force_refresh(self, mock_fetch, mock_scrape):
        """Test force refresh bypasses cache."""
        # Setup mocks
        mock_scrape.return_value = {
            "supported": ["OpenAI"],
            "unsupported": [],
        }
        mock_fetch.return_value = {
            "OpenAI": "openai",
        }

        # First call with force
        get_stream_cancellation_providers(force_refresh=True)

        self.assertTrue(mock_scrape.called)
        mock_scrape.reset_mock()

        # Second call with force - should call API again
        get_stream_cancellation_providers(force_refresh=True)

        self.assertTrue(mock_scrape.called)

    @patch('llm.provider_capabilities_service.get_stream_cancellation_providers')
    def test_supports_stream_cancellation(self, mock_get_providers):
        """Test supports_stream_cancellation function."""
        mock_get_providers.return_value = {"openai", "anthropic", "azure"}

        # Supported providers
        self.assertTrue(supports_stream_cancellation("openai"))
        self.assertTrue(supports_stream_cancellation("anthropic"))
        self.assertTrue(supports_stream_cancellation("azure"))

        # Unsupported providers
        self.assertFalse(supports_stream_cancellation("google"))
        self.assertFalse(supports_stream_cancellation("groq"))

        # Edge cases
        self.assertFalse(supports_stream_cancellation(""))
        self.assertFalse(supports_stream_cancellation(None))

    @patch('llm.provider_capabilities_service.get_stream_cancellation_providers')
    def test_supports_stream_cancellation_case_insensitive(self, mock_get_providers):
        """Test that provider checking is case-insensitive."""
        mock_get_providers.return_value = {"openai", "anthropic"}

        # Different cases should all work
        self.assertTrue(supports_stream_cancellation("openai"))
        self.assertTrue(supports_stream_cancellation("OPENAI"))
        self.assertTrue(supports_stream_cancellation("OpenAI"))
        self.assertTrue(supports_stream_cancellation("oPeNaI"))

    @patch('llm.provider_capabilities_service._scrape_streaming_docs')
    @patch('llm.provider_capabilities_service._fetch_provider_slugs')
    @patch('llm.provider_capabilities_service._load_fallback_data')
    def test_fallback_on_scraping_failure(self, mock_load_fallback, mock_fetch, mock_scrape):
        """Test that fallback JSON is used when scraping fails."""
        # Make scraping fail
        mock_scrape.side_effect = Exception("Scraping failed")
        mock_fetch.side_effect = Exception("API failed")

        # Setup fallback
        mock_load_fallback.return_value = {
            "stream_cancellation": {
                "supported_slugs": ["openai", "anthropic"],
                "source": "fallback",
            }
        }

        # Should use fallback data
        providers = get_stream_cancellation_providers(force_refresh=True)

        self.assertIn("openai", providers)
        self.assertIn("anthropic", providers)
        self.assertTrue(mock_load_fallback.called)

    def test_cache_key_isolation(self):
        """Test that cache keys don't conflict."""
        # Set a value directly in cache
        test_data = {
            "supported_slugs": ["test-provider"],
            "source": "test",
        }
        cache.set(CACHE_KEY_STREAM_CANCELLATION, test_data, 60)

        # Should retrieve the same data
        cached = cache.get(CACHE_KEY_STREAM_CANCELLATION)
        self.assertEqual(cached, test_data)

        # Other cache keys should not be affected
        cache.set("other_key", "other_value", 60)
        self.assertEqual(cache.get("other_key"), "other_value")
        self.assertEqual(cache.get(CACHE_KEY_STREAM_CANCELLATION), test_data)
