"""Audit logging tests — middleware, manager, and service layer.

Covers:
- mutations produce ``AuditLog`` rows with user / IP / request_id /
  success, and auth flows map to the right ``AUTH_*`` actions
- read-only requests are not logged
- a failure inside audit persistence NEVER breaks the request
- no secret material (passwords) is persisted in any row field
- ``AuditLogManager.log`` field routing and ``AuditLog.save`` category
  auto-derivation

``audit_logging`` is enabled app+middleware in ``settings/base`` which
the test settings inherit; ``override_settings`` is NOT needed. If the
app were disabled these tests would fail loudly rather than silently
skip — that is intentional (this is a compliance surface).

Historical production bug pinned here (fixed): ``AuditService.log_action``
passed a phantom ``project=`` kwarg to ``AuditLog.objects.create`` (the
model has no such field) and raised ``TypeError`` on every call. The
``project`` concept (dead app) has been stripped from the audit layer;
``log_action`` now genuinely writes rows.
"""

import json
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from audit_logging.models import AuditLog, AuditLogManager
from audit_logging.services import AuditService
from authentication.jwt_utils import JWTManager
from authentication.models import User

PASSWORD = "Sup3r-secret-audit-1!"


def _row_blob(row: AuditLog) -> str:
    """Serialize every persisted field of a row for leak scanning."""
    return json.dumps(
        {
            "action": row.action,
            "action_category": row.action_category,
            "user_email": row.user_email,
            "user_ip": row.user_ip,
            "user_agent": row.user_agent,
            "resource_id": row.resource_id,
            "resource_str": row.resource_str,
            "extra_data": row.extra_data,
            "request_id": row.request_id,
            "session_id": row.session_id,
            "error_message": row.error_message,
        },
        default=str,
    )


class AuditMiddlewareAuthFlowTest(TestCase):
    """Mutations through the real middleware stack produce rows."""

    def setUp(self):
        cache.clear()  # signup-guard / ratelimit buckets are shared
        self.client = APIClient()

    def test_failed_login_logged_with_ip_and_failure(self):
        response = self.client.post(
            reverse("authentication:login"),
            {"email": "ghost@example.com", "password": "wrong"},
            format="json",
            REMOTE_ADDR="10.20.30.40",
        )
        self.assertEqual(response.status_code, 400)

        row = AuditLog.objects.get(action="AUTH_LOGIN")
        self.assertFalse(row.success)
        self.assertIsNone(row.user)
        self.assertEqual(row.user_ip, "10.20.30.40")
        self.assertEqual(row.extra_data["method"], "POST")
        self.assertEqual(row.extra_data["path"], "/api/auth/login/")
        self.assertEqual(row.extra_data["status_code"], 400)
        self.assertIsNotNone(row.duration_ms)

    def test_successful_login_logged_as_success(self):
        User.objects.create_user(
            email="alice@example.com", password=PASSWORD, is_verified=True
        )
        response = self.client.post(
            reverse("authentication:login"),
            {"email": "alice@example.com", "password": PASSWORD},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        row = AuditLog.objects.get(action="AUTH_LOGIN")
        self.assertTrue(row.success)
        self.assertEqual(row.extra_data["status_code"], 200)

    def test_logout_logged_with_authenticated_user(self):
        user = User.objects.create_user(
            email="bob@example.com", password=PASSWORD, is_verified=True
        )
        token = JWTManager.create_access_token(user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        response = self.client.post(reverse("authentication:logout"))
        self.assertEqual(response.status_code, 200)

        row = AuditLog.objects.get(action="AUTH_LOGOUT")
        self.assertTrue(row.success)
        self.assertEqual(row.user_id, user.id)
        self.assertEqual(row.user_email, user.email)  # snapshot on save

    def test_register_logged(self):
        response = self.client.post(
            reverse("authentication:register"),
            {
                "email": "carol@example.com",
                "password": PASSWORD,
                "password_confirm": PASSWORD,
                "full_name": "Carol Test",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        row = AuditLog.objects.get(action="AUTH_REGISTER")
        self.assertTrue(row.success)
        self.assertEqual(row.action_category, "AUTH")

    def test_password_reset_logged(self):
        response = self.client.post(
            reverse("authentication:password-reset"),
            {"email": "nobody@example.com"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            AuditLog.objects.filter(action="AUTH_PASSWORD_RESET").exists()
        )

    def test_request_id_correlated_from_header(self):
        self.client.post(
            reverse("authentication:login"),
            {"email": "ghost@example.com", "password": "wrong"},
            format="json",
            HTTP_X_REQUEST_ID="rid-abc-123",
        )
        row = AuditLog.objects.get(action="AUTH_LOGIN")
        self.assertEqual(row.request_id, "rid-abc-123")

    def test_request_id_generated_when_absent(self):
        self.client.post(
            reverse("authentication:login"),
            {"email": "ghost@example.com", "password": "wrong"},
            format="json",
        )
        row = AuditLog.objects.get(action="AUTH_LOGIN")
        self.assertTrue(row.request_id)  # RequestIDMiddleware minted one

    def test_get_requests_not_logged(self):
        user = User.objects.create_user(
            email="dave@example.com", password=PASSWORD, is_verified=True
        )
        token = JWTManager.create_access_token(user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        response = self.client.get(reverse("authentication:profile"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(AuditLog.objects.count(), 0)

    def test_failed_request_records_error_message(self):
        # Unauthenticated logout -> DRF 401 with a "detail" body, which
        # the middleware extracts into error_message.
        response = self.client.post(reverse("authentication:logout"))
        self.assertEqual(response.status_code, 401)
        row = AuditLog.objects.get(action="AUTH_LOGOUT")
        self.assertFalse(row.success)
        self.assertIn("credentials", row.error_message)


class AuditMiddlewareResilienceTest(TestCase):
    """Audit persistence failures are swallowed, never break requests."""

    def setUp(self):
        cache.clear()
        self.client = APIClient()

    def test_log_write_exception_does_not_break_request(self):
        with patch.object(
            AuditLogManager, "log", side_effect=RuntimeError("db down")
        ):
            response = self.client.post(
                reverse("authentication:login"),
                {"email": "ghost@example.com", "password": "wrong"},
                format="json",
            )
        # The view's own response comes through untouched.
        self.assertEqual(response.status_code, 400)
        self.assertEqual(AuditLog.objects.count(), 0)

    def test_log_write_exception_on_success_path(self):
        User.objects.create_user(
            email="erin@example.com", password=PASSWORD, is_verified=True
        )
        with patch.object(
            AuditLogManager, "log", side_effect=RuntimeError("db down")
        ):
            response = self.client.post(
                reverse("authentication:login"),
                {"email": "erin@example.com", "password": PASSWORD},
                format="json",
            )
        self.assertEqual(response.status_code, 200)
        self.assertIn("access_token", response.data)


class AuditNoSecretMaterialTest(TestCase):
    """No password (or other secret) may ever be persisted in a row."""

    def setUp(self):
        cache.clear()
        self.client = APIClient()

    def test_login_password_not_persisted(self):
        self.client.post(
            reverse("authentication:login"),
            {"email": "ghost@example.com", "password": PASSWORD},
            format="json",
        )
        row = AuditLog.objects.get(action="AUTH_LOGIN")
        self.assertNotIn(PASSWORD, _row_blob(row))

    def test_register_password_not_persisted(self):
        self.client.post(
            reverse("authentication:register"),
            {
                "email": "frank@example.com",
                "password": PASSWORD,
                "password_confirm": PASSWORD,
                "full_name": "Frank Test",
            },
            format="json",
        )
        for row in AuditLog.objects.all():
            self.assertNotIn(PASSWORD, _row_blob(row))

    def test_password_in_query_params_not_persisted(self):
        # extra_data stores query_params; a secret passed there must not
        # survive. (Defense-in-depth: clients should never do this.)
        self.client.post(
            reverse("authentication:login") + f"?password={PASSWORD}",
            {"email": "ghost@example.com", "password": PASSWORD},
            format="json",
        )
        row = AuditLog.objects.get(action="AUTH_LOGIN")
        self.assertNotIn(PASSWORD, _row_blob(row))


class AuditManagerAndModelTest(TestCase):
    def test_manager_log_routes_reserved_fields(self):
        user = User.objects.create_user(
            email="grace@example.com", password=PASSWORD
        )
        row = AuditLog.objects.log(
            action="AUTH_LOGIN",
            user=user,
            user_ip="192.0.2.7",
            request_id="rid-1",
            session_id="sess-1",
            success=False,
            duration_ms=12,
            error_message="bad credentials",
            extra_data={"method": "POST"},
        )
        row.refresh_from_db()
        self.assertEqual(row.user_ip, "192.0.2.7")
        self.assertEqual(row.request_id, "rid-1")
        self.assertEqual(row.session_id, "sess-1")
        self.assertFalse(row.success)
        self.assertEqual(row.duration_ms, 12)
        self.assertEqual(row.error_message, "bad credentials")
        self.assertEqual(row.extra_data, {"method": "POST"})
        # Reserved fields must not leak into extra_data.
        self.assertNotIn("user_ip", row.extra_data)

    def test_save_derives_category_and_email_snapshot(self):
        user = User.objects.create_user(
            email="heidi@example.com", password=PASSWORD
        )
        row = AuditLog.objects.create(action="AUTH_LOGIN", user=user)
        self.assertEqual(row.action_category, "AUTH")
        self.assertEqual(row.user_email, "heidi@example.com")

    def test_user_deletion_keeps_row_with_snapshot(self):
        user = User.objects.create_user(
            email="ivan@example.com", password=PASSWORD
        )
        row = AuditLog.objects.create(action="AUTH_LOGIN", user=user)
        user.delete()
        row.refresh_from_db()
        self.assertIsNone(row.user)  # SET_NULL
        self.assertEqual(row.user_email, "ivan@example.com")


class AuditServiceTest(TestCase):
    def test_get_user_activity_filters_by_user(self):
        alice = User.objects.create_user(email="a@example.com", password="x1!Aa111")
        bob = User.objects.create_user(email="b@example.com", password="x1!Aa111")
        AuditLog.objects.create(action="AUTH_LOGIN", user=alice)
        AuditLog.objects.create(action="AUTH_LOGIN", user=bob)
        logs = AuditService.get_user_activity(alice)
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0].user_id, alice.id)

    def test_get_failed_actions(self):
        AuditLog.objects.create(action="AUTH_LOGIN", success=False)
        AuditLog.objects.create(action="AUTH_LOGIN", success=True)
        failed = AuditService.get_failed_actions()
        self.assertEqual(len(failed), 1)
        self.assertFalse(failed[0].success)

    def test_log_action_writes_row(self):
        """``log_action`` persists a row (it used to raise TypeError on
        every call via a phantom ``project=`` kwarg). The kwargs mirror
        the subscription plan-change call site
        (``usage_quota/services/subscription_service.py::_audit``)."""
        user = User.objects.create_user(
            email="judy@example.com", password=PASSWORD
        )
        row = AuditService.log_action(
            action="subscription_plan_change",
            user=user,
            from_plan="free",
            to_plan="plus",
            initiated_by="admin",
            reason="ops request",
        )
        row.refresh_from_db()
        self.assertEqual(row.action, "subscription_plan_change")
        self.assertEqual(row.user_id, user.id)
        self.assertEqual(row.user_email, user.email)
        self.assertTrue(row.success)
        self.assertEqual(
            row.extra_data,
            {
                "from_plan": "free",
                "to_plan": "plus",
                "initiated_by": "admin",
                "reason": "ops request",
            },
        )

    def test_log_action_failure_path(self):
        row = AuditService.log_action(
            action="AUTH_LOGIN",
            success=False,
            error_message="bad credentials",
        )
        row.refresh_from_db()
        self.assertFalse(row.success)
        self.assertEqual(row.error_message, "bad credentials")
        self.assertEqual(row.action_category, "AUTH")
