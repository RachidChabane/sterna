"""Tests for the support request API."""
import pytest
from unittest.mock import patch, MagicMock
from rest_framework.test import APIClient
from authentication.models import User
from support.models import SupportRequest


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def user(db):
    return User.objects.create_user(
        email="test@example.com",
        password="testpass123",
        full_name="Test User",
    )


@pytest.fixture
def auth_client(api_client, user):
    api_client.force_authenticate(user=user)
    return api_client


URL = "/api/support/requests/"


@pytest.mark.django_db
class TestSupportRequestCreate:
    def test_authenticated_submit_creates_row(self, auth_client, user):
        with patch("support.views.support_notifications") as mock_notif:
            mock_notif.send_support_request_received_email = MagicMock()
            mock_notif.post_to_slack = MagicMock()
            resp = auth_client.post(URL, {
                "email": user.email,
                "subject": "Something broke",
                "message": "It is completely broken please help",
                "context": {"route": "/chats", "plan": "pro"},
            }, format="json")
        assert resp.status_code == 201
        assert SupportRequest.objects.filter(user=user).count() == 1
        instance = SupportRequest.objects.get(user=user)
        assert instance.subject == "Something broke"
        assert instance.status == "new"

    def test_authenticated_submit_sends_ack_email(self, auth_client, user):
        with patch("support.views.support_notifications.send_support_request_received_email") as mock_email, \
             patch("support.views.support_notifications.post_to_slack"):
            auth_client.post(URL, {
                "email": user.email,
                "subject": "Test",
                "message": "Test message body here",
            }, format="json")
        mock_email.assert_called_once()

    def test_authenticated_submit_posts_to_slack(self, auth_client, user):
        with patch("support.views.support_notifications.send_support_request_received_email"), \
             patch("support.views.support_notifications.post_to_slack") as mock_slack:
            auth_client.post(URL, {
                "email": user.email,
                "subject": "Test",
                "message": "Test message body here",
            }, format="json")
        mock_slack.assert_called_once()

    def test_anon_submit_allowed_with_email(self, api_client):
        with patch("support.views.support_notifications.send_support_request_received_email"), \
             patch("support.views.support_notifications.post_to_slack"):
            resp = api_client.post(URL, {
                "email": "anon@example.com",
                "subject": "Help me",
                "message": "I have a big problem here",
            }, format="json")
        assert resp.status_code == 201
        instance = SupportRequest.objects.get(email="anon@example.com")
        assert instance.user is None

    def test_notification_failure_does_not_break_submission(self, auth_client, user):
        with patch("support.views.support_notifications.send_support_request_received_email",
                   side_effect=Exception("SMTP down")), \
             patch("support.views.support_notifications.post_to_slack",
                   side_effect=Exception("Slack down")):
            resp = auth_client.post(URL, {
                "email": user.email,
                "subject": "Test",
                "message": "Test message body here",
            }, format="json")
        assert resp.status_code == 201

    def test_message_too_short_rejected(self, api_client):
        resp = api_client.post(URL, {
            "email": "test@example.com",
            "subject": "Short",
            "message": "hi",
        }, format="json")
        assert resp.status_code == 400

    def test_rate_limit_honored(self, api_client, db):
        """After 3 anon submissions within hour, 4th returns 429."""
        from django.core.cache import cache
        from django.test import override_settings
        from django.conf import settings as django_settings
        from rest_framework.throttling import SimpleRateThrottle
        from rest_framework.settings import api_settings as drf_settings
        new_rf = {
            **django_settings.REST_FRAMEWORK,
            "DEFAULT_THROTTLE_RATES": {
                **django_settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"],
                "support_anon": "3/hour",
            },
        }
        cache.clear()
        with override_settings(REST_FRAMEWORK=new_rf):
            # DRF caches THROTTLE_RATES at class level; force refresh after override
            if hasattr(drf_settings, "DEFAULT_THROTTLE_RATES"):
                delattr(drf_settings, "DEFAULT_THROTTLE_RATES")
            SimpleRateThrottle.THROTTLE_RATES = drf_settings.DEFAULT_THROTTLE_RATES
            with patch("support.views.support_notifications.send_support_request_received_email"), \
                 patch("support.views.support_notifications.post_to_slack"):
                for i in range(3):
                    resp = api_client.post(URL, {
                        "email": f"user{i}@example.com",
                        "subject": f"Request {i}",
                        "message": "Testing rate limit here",
                    }, format="json")
                    assert resp.status_code == 201
                resp = api_client.post(URL, {
                    "email": "over@example.com",
                    "subject": "Over limit",
                    "message": "Testing rate limit here",
                }, format="json")
                assert resp.status_code == 429
