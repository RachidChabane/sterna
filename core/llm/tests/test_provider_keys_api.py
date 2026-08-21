"""Tests for the provider-scoped BYOK key settings endpoints.

GET    /api/settings/provider-keys/            -> list w/ configured + masked_key
PUT    /api/settings/provider-keys/<provider>/ -> set key (masked in response)
POST   /api/settings/provider-keys/<provider>/ -> same as PUT
DELETE /api/settings/provider-keys/<provider>/ -> remove key

The full key must never appear in any response.
"""

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from authentication.models import User
from llm.provider_registry import BYOK_PROVIDERS

LIST_URL = reverse('settings:provider-keys')


def detail_url(provider: str) -> str:
    return reverse('settings:provider-key-detail', kwargs={'provider': provider})


@pytest.fixture
def user(db):
    return User.objects.create_user(email='provider-keys@test.com', password='x')


@pytest.fixture
def client(user):
    c = APIClient()
    c.force_authenticate(user=user)
    return c


@pytest.mark.django_db
class TestAuthRequired:
    def test_list_requires_auth(self):
        resp = APIClient().get(LIST_URL)
        assert resp.status_code in (401, 403)

    def test_put_requires_auth(self):
        resp = APIClient().put(
            detail_url('anthropic'), {'api_key': 'sk-ant-x'}, format='json',
        )
        assert resp.status_code in (401, 403)

    def test_delete_requires_auth(self):
        resp = APIClient().delete(detail_url('anthropic'))
        assert resp.status_code in (401, 403)


@pytest.mark.django_db
class TestListProviderKeys:
    def test_lists_all_registry_providers_unconfigured(self, client):
        resp = client.get(LIST_URL)
        assert resp.status_code == 200
        providers = resp.json()['providers']
        assert {p['provider'] for p in providers} == set(BYOK_PROVIDERS)
        for p in providers:
            assert p['configured'] is False
            assert p['masked_key'] is None
            assert p['label'] == BYOK_PROVIDERS[p['provider']]['label']

    def test_configured_provider_shows_masked_key_only(self, client, user):
        user.set_provider_key('anthropic', 'sk-ant-secret-key-1234')
        user.save()

        resp = client.get(LIST_URL)
        assert resp.status_code == 200
        by_slug = {p['provider']: p for p in resp.json()['providers']}
        assert by_slug['anthropic']['configured'] is True
        assert by_slug['anthropic']['masked_key'] == '****1234'
        assert 'sk-ant-secret-key-1234' not in resp.content.decode()


@pytest.mark.django_db
class TestSetProviderKey:
    def test_put_sets_key_and_masks_response(self, client, user):
        resp = client.put(
            detail_url('anthropic'),
            {'api_key': 'sk-ant-secret-key-1234'},
            format='json',
        )
        assert resp.status_code == 200, resp.content
        body = resp.json()
        assert body['configured'] is True
        assert body['masked_key'] == '****1234'
        assert 'sk-ant-secret-key-1234' not in resp.content.decode()

        user.refresh_from_db()
        assert user.get_provider_key('anthropic') == 'sk-ant-secret-key-1234'

    def test_post_behaves_like_put(self, client, user):
        resp = client.post(
            detail_url('openai'), {'api_key': 'sk-proj-abcd'}, format='json',
        )
        assert resp.status_code == 200, resp.content
        user.refresh_from_db()
        assert user.get_provider_key('openai') == 'sk-proj-abcd'

    def test_unknown_provider_404(self, client):
        resp = client.put(
            detail_url('meta-llama'), {'api_key': 'whatever'}, format='json',
        )
        assert resp.status_code == 404

    def test_empty_key_400(self, client):
        resp = client.put(detail_url('anthropic'), {'api_key': '  '}, format='json')
        assert resp.status_code == 400

    def test_missing_key_400(self, client):
        resp = client.put(detail_url('anthropic'), {}, format='json')
        assert resp.status_code == 400

    def test_obviously_wrong_prefix_400(self, client, user):
        resp = client.put(
            detail_url('anthropic'), {'api_key': 'not-an-anthropic-key'}, format='json',
        )
        assert resp.status_code == 400
        user.refresh_from_db()
        assert user.get_provider_key('anthropic') is None

    def test_mistral_has_no_prefix_check(self, client, user):
        resp = client.put(
            detail_url('mistralai'), {'api_key': 'anyOpaqueToken123'}, format='json',
        )
        assert resp.status_code == 200, resp.content
        user.refresh_from_db()
        assert user.get_provider_key('mistralai') == 'anyOpaqueToken123'

    def test_set_does_not_clobber_other_providers(self, client, user):
        user.set_provider_key('openai', 'sk-keep-me-0001')
        user.save()

        resp = client.put(
            detail_url('anthropic'), {'api_key': 'sk-ant-new-0002'}, format='json',
        )
        assert resp.status_code == 200
        user.refresh_from_db()
        assert user.get_provider_key('openai') == 'sk-keep-me-0001'
        assert user.get_provider_key('anthropic') == 'sk-ant-new-0002'


@pytest.mark.django_db
class TestDeleteProviderKey:
    def test_delete_removes_key(self, client, user):
        user.set_provider_key('anthropic', 'sk-ant-secret')
        user.save()

        resp = client.delete(detail_url('anthropic'))
        assert resp.status_code == 200
        assert resp.json()['configured'] is False

        user.refresh_from_db()
        assert user.get_provider_key('anthropic') is None

    def test_delete_unknown_provider_404(self, client):
        resp = client.delete(detail_url('nope'))
        assert resp.status_code == 404

    def test_delete_unset_provider_is_ok(self, client):
        resp = client.delete(detail_url('anthropic'))
        assert resp.status_code == 200
