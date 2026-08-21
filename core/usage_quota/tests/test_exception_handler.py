"""End-to-end: DRF exception handler maps billing exceptions to 402.

Exercises the gate via POST /api/code-sessions/sessions/<id>/jobs/.
Free tier has code_sessions=False, so ``_create_job``'s check_quota
raises ``FeatureNotAvailable`` → handler → 402.
"""
import pytest
from rest_framework.test import APIClient

from code_sessions.models import CodeSession
from usage_quota._tier_seed import seed_tiers_for_tests
from usage_quota.models import SubscriptionPlan, UserSubscription


@pytest.mark.django_db
def test_402_for_feature_not_available(django_user_model):
    seed_tiers_for_tests()
    user = django_user_model.objects.create_user(
        email='free@t.com', password='x',
    )
    UserSubscription.objects.create(
        user=user,
        plan=SubscriptionPlan.objects.get(name='free'),
    )
    session = CodeSession.objects.create(
        user=user,
        name='test-session',
        github_repo_full_name='x/y',
    )

    client = APIClient()
    client.force_authenticate(user=user)
    resp = client.post(
        f'/api/code-sessions/sessions/{session.id}/jobs/',
        data={'prompt': 'do nothing'},
        format='json',
    )
    assert resp.status_code == 402, resp.content
    body = resp.json()
    assert body['error'] == 'feature_not_available'
    assert body['details']['plan_slug'] == 'free'
    assert body['details']['upgrade_url'] == '/pricing'
