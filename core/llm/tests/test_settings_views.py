"""Regression test: POST /api/settings/openrouter/ resets provisioning markers.

Without the reset, a previously-provisioned user who uploads their own
key gets double-billed (their OpenRouter account + their Sterna
weekly quota). See review-1.md #1 and Step 4.2 of the task-8 plan.
"""

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from authentication.models import User


@pytest.mark.django_db
def test_post_byok_resets_provisioned_at():
    u = User.objects.create_user(email='switch@test.com', password='x')
    u.openrouter_api_key = 'sk-or-platform-provisioned'
    u.openrouter_key_provisioned_at = timezone.now()
    u.openrouter_key_hash = 'oldplatformhash'
    u.save()

    client = APIClient()
    client.force_authenticate(user=u)
    resp = client.post(
        reverse('settings:openrouter'),
        {'api_key': 'sk-or-user-uploaded-XXXX'},
        format='json',
    )
    assert resp.status_code == 200, resp.content

    u.refresh_from_db()
    assert u.openrouter_api_key == 'sk-or-user-uploaded-XXXX'
    assert u.openrouter_key_provisioned_at is None
    assert u.openrouter_key_hash is None
