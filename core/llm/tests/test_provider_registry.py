"""Tests for llm.provider_registry (provider-scoped BYOK model mapping)."""

from llm.provider_registry import (
    BYOK_PROVIDERS,
    OPENROUTER_BASE_URL,
    is_openrouter_url,
    native_model_name,
    provider_base_url,
    provider_for_model,
)


class TestProviderForModel:
    def test_first_party_prefixes_map_to_slug(self):
        assert provider_for_model('openai/gpt-4o') == 'openai'
        assert provider_for_model('anthropic/claude-sonnet-4.5') == 'anthropic'
        assert provider_for_model('google/gemini-2.5-pro') == 'google'
        assert provider_for_model('mistralai/mistral-large') == 'mistralai'
        assert provider_for_model('deepseek/deepseek-chat') == 'deepseek'
        assert provider_for_model('x-ai/grok-4') == 'x-ai'

    def test_variant_suffix_does_not_change_provider(self):
        assert provider_for_model('anthropic/claude-sonnet-4.5:thinking') == 'anthropic'
        assert provider_for_model('openai/gpt-4o:online') == 'openai'

    def test_non_first_party_prefixes_are_not_eligible(self):
        assert provider_for_model('meta-llama/llama-3.3-70b-instruct') is None
        assert provider_for_model('qwen/qwen-2.5-72b-instruct') is None
        assert provider_for_model('openrouter/auto') is None

    def test_models_without_slash_are_not_eligible(self):
        assert provider_for_model('gpt-4o') is None
        assert provider_for_model('claude-sonnet-4.5') is None

    def test_empty_and_none_are_not_eligible(self):
        assert provider_for_model(None) is None
        assert provider_for_model('') is None


class TestNativeModelName:
    def test_strips_provider_prefix(self):
        assert native_model_name('openai/gpt-4o') == 'gpt-4o'
        assert native_model_name('anthropic/claude-sonnet-4.5') == 'claude-sonnet-4.5'

    def test_strips_variant_suffix(self):
        assert native_model_name('anthropic/claude-sonnet-4.5:thinking') == 'claude-sonnet-4.5'
        assert native_model_name('openai/gpt-4o:online') == 'gpt-4o'

    def test_model_without_prefix_only_loses_suffix(self):
        assert native_model_name('gpt-4o') == 'gpt-4o'
        assert native_model_name('gpt-4o:online') == 'gpt-4o'

    def test_none_and_empty_pass_through(self):
        assert native_model_name(None) is None
        assert native_model_name('') == ''


class TestRegistryShape:
    def test_all_entries_have_label_and_https_base_url(self):
        for slug, cfg in BYOK_PROVIDERS.items():
            assert cfg['label'], slug
            assert cfg['base_url'].startswith('https://'), slug

    def test_provider_base_url_lookup(self):
        assert provider_base_url('openai') == 'https://api.openai.com/v1'
        assert provider_base_url('anthropic') == 'https://api.anthropic.com/v1'
        assert (
            provider_base_url('google')
            == 'https://generativelanguage.googleapis.com/v1beta/openai'
        )


class TestIsOpenRouterUrl:
    def test_openrouter_urls(self):
        assert is_openrouter_url(OPENROUTER_BASE_URL) is True
        assert is_openrouter_url(None) is True
        assert is_openrouter_url('') is True

    def test_direct_provider_urls(self):
        assert is_openrouter_url('https://api.openai.com/v1') is False
        assert is_openrouter_url('https://api.anthropic.com/v1') is False
