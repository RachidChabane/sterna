"""Tests for APIKeyResolver.resolve_endpoint / resolve_with_origin(model_id=...).

Priority order under test:
  a. provider-scoped BYOK key (model maps to first-party provider AND
     user holds a key for it) -> direct provider endpoint, 'byok'
  b. user OpenRouter key (BYOK iff provisioned_at IS NULL)
  c. platform fallback key -> OpenRouter, 'platform'
"""

import pytest
from django.utils import timezone

from authentication.models import User
from llm.provider_registry import OPENROUTER_BASE_URL
from llm.services.api_key_resolver import APIKeyResolver


@pytest.fixture
def resolver():
    r = APIKeyResolver()
    r._fallback_key = 'sk-or-platform-fallback'
    return r


@pytest.fixture
def resolver_no_fallback():
    r = APIKeyResolver()
    r._fallback_key = ''
    return r


@pytest.fixture
def user(db):
    u = User.objects.create_user(email='byok@test.com', password='x')
    # The post_save signal may auto-provision an OpenRouter key when
    # OPENROUTER_PROVISIONING_KEY is configured — reset to a clean slate
    # so each test controls the key state explicitly.
    u.openrouter_api_key = None
    u.openrouter_key_provisioned_at = None
    u.openrouter_key_hash = None
    u.save()
    return u


@pytest.mark.django_db
class TestResolveEndpointPriority:
    def test_provider_key_beats_openrouter_byok(self, resolver, user):
        user.openrouter_api_key = 'sk-or-user-byok'
        user.set_provider_key('anthropic', 'sk-ant-user-key')
        user.save()

        key, base_url, origin, slug = resolver.resolve_endpoint(
            user=user, model_id='anthropic/claude-sonnet-4.5',
        )
        assert key == 'sk-ant-user-key'
        assert base_url == 'https://api.anthropic.com/v1'
        assert origin == 'byok'
        assert slug == 'anthropic'

    def test_variant_suffix_still_matches_provider_key(self, resolver, user):
        user.set_provider_key('anthropic', 'sk-ant-user-key')
        user.save()

        key, base_url, origin, slug = resolver.resolve_endpoint(
            user=user, model_id='anthropic/claude-sonnet-4.5:thinking',
        )
        assert key == 'sk-ant-user-key'
        assert slug == 'anthropic'

    def test_provider_key_for_other_provider_is_ignored(self, resolver, user):
        user.openrouter_api_key = 'sk-or-user-byok'
        user.set_provider_key('anthropic', 'sk-ant-user-key')
        user.save()

        key, base_url, origin, slug = resolver.resolve_endpoint(
            user=user, model_id='openai/gpt-4o',
        )
        assert key == 'sk-or-user-byok'
        assert base_url == OPENROUTER_BASE_URL
        assert origin == 'byok'
        assert slug is None

    def test_non_first_party_model_ignores_provider_keys(self, resolver, user):
        user.openrouter_api_key = 'sk-or-user-byok'
        user.set_provider_key('anthropic', 'sk-ant-user-key')
        user.save()

        key, base_url, origin, slug = resolver.resolve_endpoint(
            user=user, model_id='meta-llama/llama-3.3-70b-instruct',
        )
        assert key == 'sk-or-user-byok'
        assert base_url == OPENROUTER_BASE_URL
        assert origin == 'byok'
        assert slug is None

    def test_openrouter_byok_beats_platform_fallback(self, resolver, user):
        user.openrouter_api_key = 'sk-or-user-byok'
        user.openrouter_key_provisioned_at = None
        user.save()

        key, base_url, origin, slug = resolver.resolve_endpoint(
            user=user, model_id='anthropic/claude-sonnet-4.5',
        )
        assert key == 'sk-or-user-byok'
        assert base_url == OPENROUTER_BASE_URL
        assert origin == 'byok'
        assert slug is None

    def test_provisioned_openrouter_key_is_platform(self, resolver, user):
        user.openrouter_api_key = 'sk-or-provisioned'
        user.openrouter_key_provisioned_at = timezone.now()
        user.save()

        key, base_url, origin, slug = resolver.resolve_endpoint(
            user=user, model_id='anthropic/claude-sonnet-4.5',
        )
        assert key == 'sk-or-provisioned'
        assert origin == 'platform'
        assert slug is None

    def test_platform_fallback_when_user_has_no_keys(self, resolver, user):
        key, base_url, origin, slug = resolver.resolve_endpoint(
            user=user, model_id='anthropic/claude-sonnet-4.5',
        )
        assert key == 'sk-or-platform-fallback'
        assert base_url == OPENROUTER_BASE_URL
        assert origin == 'platform'
        assert slug is None

    def test_no_model_id_skips_provider_branch(self, resolver, user):
        user.openrouter_api_key = 'sk-or-user-byok'
        user.set_provider_key('anthropic', 'sk-ant-user-key')
        user.save()

        key, base_url, origin, slug = resolver.resolve_endpoint(user=user)
        assert key == 'sk-or-user-byok'
        assert base_url == OPENROUTER_BASE_URL
        assert slug is None

    def test_anonymous_uses_fallback(self, resolver):
        key, base_url, origin, slug = resolver.resolve_endpoint(
            user=None, model_id='anthropic/claude-sonnet-4.5',
        )
        assert key == 'sk-or-platform-fallback'
        assert origin == 'platform'

    def test_raises_when_no_key_available(self, resolver_no_fallback, user):
        with pytest.raises(ValueError):
            resolver_no_fallback.resolve_endpoint(
                user=user, model_id='anthropic/claude-sonnet-4.5',
            )


@pytest.mark.django_db
class TestResolveWithOriginModelId:
    def test_model_id_matches_resolve_endpoint_origin(self, resolver, user):
        # A provisioned user (platform via OpenRouter rule) with an
        # anthropic provider key must be 'byok' for anthropic models.
        user.openrouter_api_key = 'sk-or-provisioned'
        user.openrouter_key_provisioned_at = timezone.now()
        user.set_provider_key('anthropic', 'sk-ant-user-key')
        user.save()

        key, origin = resolver.resolve_with_origin(
            user=user, model_id='anthropic/claude-sonnet-4.5',
        )
        assert key == 'sk-ant-user-key'
        assert origin == 'byok'

        ep_key, _url, ep_origin, _slug = resolver.resolve_endpoint(
            user=user, model_id='anthropic/claude-sonnet-4.5',
        )
        assert (key, origin) == (ep_key, ep_origin)

    def test_model_id_non_matching_model_keeps_openrouter_origin(self, resolver, user):
        user.openrouter_api_key = 'sk-or-provisioned'
        user.openrouter_key_provisioned_at = timezone.now()
        user.set_provider_key('anthropic', 'sk-ant-user-key')
        user.save()

        key, origin = resolver.resolve_with_origin(
            user=user, model_id='meta-llama/llama-3.3-70b-instruct',
        )
        assert key == 'sk-or-provisioned'
        assert origin == 'platform'

    def test_backward_compatible_without_model_id(self, resolver, user):
        user.openrouter_api_key = 'sk-or-user-byok'
        user.set_provider_key('anthropic', 'sk-ant-user-key')
        user.save()

        key, origin = resolver.resolve_with_origin(user=user)
        assert key == 'sk-or-user-byok'
        assert origin == 'byok'


@pytest.mark.django_db
class TestUserProviderKeyHelpers:
    def test_set_get_delete_roundtrip(self, user):
        assert user.get_provider_key('anthropic') is None
        user.set_provider_key('anthropic', 'sk-ant-abc')
        user.set_provider_key('openai', 'sk-openai-def')
        user.save()

        user.refresh_from_db()
        assert user.get_provider_key('anthropic') == 'sk-ant-abc'
        assert user.get_provider_key('openai') == 'sk-openai-def'

        user.delete_provider_key('anthropic')
        user.save()
        user.refresh_from_db()
        assert user.get_provider_key('anthropic') is None
        assert user.get_provider_key('openai') == 'sk-openai-def'

    def test_delete_last_key_nulls_field(self, user):
        user.set_provider_key('openai', 'sk-abc')
        user.delete_provider_key('openai')
        assert user.provider_api_keys is None
        assert user.get_provider_key('openai') is None

    def test_corrupt_json_is_tolerated(self, user):
        user.provider_api_keys = 'not-json{{{'
        assert user.get_provider_key('openai') is None
        # set on top of corrupt data starts fresh
        user.set_provider_key('openai', 'sk-new')
        assert user.get_provider_key('openai') == 'sk-new'

    def test_non_dict_json_is_tolerated(self, user):
        user.provider_api_keys = '["a", "b"]'
        assert user.get_provider_key('openai') is None

    def test_delete_missing_provider_is_noop(self, user):
        user.delete_provider_key('openai')  # must not raise
        assert user.get_provider_key('openai') is None
