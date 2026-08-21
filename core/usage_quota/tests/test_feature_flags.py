from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status
from authentication.models import User


class FeatureFlagsViewTest(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.url = reverse('usage_quota:feature-flags')
        self.user = User.objects.create_user(
            email='user@test.com', password='pass', is_staff=False
        )
        self.admin = User.objects.create_user(
            email='admin@test.com', password='pass', is_staff=True
        )

    def test_unauthenticated_returns_401(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_regular_user_sees_beta_features(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        features = response.data['features']
        self.assertIn('spark_deploy', features)
        self.assertEqual(features['spark_deploy'], 'beta')

    def test_regular_user_does_not_see_hidden_features(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.get(self.url)
        features = response.data['features']
        self.assertNotIn('mcp_remote', features)

    def test_admin_user_sees_hidden_features(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.get(self.url)
        features = response.data['features']
        self.assertIn('mcp_remote', features)
        self.assertEqual(features['mcp_remote'], 'hidden')

    def test_all_beta_features_present_for_regular_user(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.get(self.url)
        features = response.data['features']
        expected_beta = {'spark_deploy', 'knowledge_base', 'coding_agent', 'mcp_local', 'video_generation'}
        for key in expected_beta:
            self.assertIn(key, features)
            self.assertEqual(features[key], 'beta')


class GetReleaseStagesTest(TestCase):
    def test_non_admin_filters_hidden(self):
        from usage_quota.feature_flags import get_release_stages
        stages = get_release_stages(is_admin=False)
        self.assertNotIn('mcp_remote', stages)

    def test_admin_includes_hidden(self):
        from usage_quota.feature_flags import get_release_stages
        stages = get_release_stages(is_admin=True)
        self.assertIn('mcp_remote', stages)
        self.assertEqual(stages['mcp_remote'], 'hidden')
