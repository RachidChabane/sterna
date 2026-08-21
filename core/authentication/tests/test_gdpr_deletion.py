"""GDPR Art. 17 — account deletion tests (task 16).

Covers:
- deletion request guards (auth, email confirmation, password check)
- grace-window state: PENDING row, 7-day schedule, account deactivated,
  refresh tokens revoked, JWT no longer usable
- cancel path (token validation + the happy path: request CANCELED,
  user reactivated, token spent)
- hard-delete task: cascade vs SET_NULL semantics, BillingSummary
  retention (anonymized, no PII), failure rollback

Historical production bugs pinned here (both fixed):
1. ``AccountDeletionCancelView.post`` was truncated — after loading
   the request row it never canceled/reactivated and returned ``None``
   (Django 500). Now implemented; the happy-path test asserts it.
2. ``authentication/tasks.py`` imported ``send_data_export_ready_email``
   and ``send_account_deleted_email`` from ``notifications.services``
   before they existed. Both now exist (direct tests live in
   ``notifications/tests/test_services.py``); the ``create=True`` on
   the patches here is kept for historical symmetry only.
"""

from contextlib import contextmanager
from datetime import timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from django.urls import reverse
from django.utils import timezone

from authentication.jwt_utils import JWTManager
from authentication.models import (
    AccountDeletionRequest,
    BillingSummary,
    DataExportRequest,
    RefreshToken,
    User,
)
from authentication.services.billing_anonymization import anonymize_user_id
from authentication.tasks import hard_delete_account
from authentication.tokens import create_cancel_deletion_token
from usage_quota.models import UsageLog

pytestmark = pytest.mark.django_db

DELETE_URL = reverse("authentication:account-delete-request")
CANCEL_URL = reverse("authentication:account-delete-cancel")
PROFILE_URL = reverse("authentication:profile")

PASSWORD = "Sup3r-secret!"
TEST_PEPPER = "test-pepper-do-not-rotate"


@contextmanager
def _deletion_email_mock():
    with patch(
        "notifications.services.send_account_deletion_confirmation"
    ) as m:
        yield m


@contextmanager
def _hard_delete_mocks(storage=None):
    """Mock R2 + final email for the ``hard_delete_account`` task."""
    if storage is None:
        storage = MagicMock()
        r2 = storage._get_r2_client.return_value
        r2.list_objects_v2.return_value = {"Contents": [], "IsTruncated": False}
        storage.config.bucket_name = "test-bucket"
    with patch(
        "workspaces.services.workspace_storage.get_storage_service",
        return_value=storage,
    ), patch(
        "notifications.services.send_account_deleted_email",
        create=True,
    ) as send_email:
        yield storage, send_email


class TestDeletionRequestGuards:
    def test_anonymous_rejected(self, api_client):
        assert api_client.post(DELETE_URL).status_code == 401

    def test_email_confirmation_must_match(
        self, api_client, auth_as, verified_user
    ):
        auth_as(api_client, verified_user)
        response = api_client.post(
            DELETE_URL,
            {"confirm_email": "wrong@example.com", "password": PASSWORD},
            format="json",
        )
        assert response.status_code == 400
        assert not AccountDeletionRequest.objects.exists()

    def test_wrong_password_rejected(self, api_client, auth_as, verified_user):
        auth_as(api_client, verified_user)
        response = api_client.post(
            DELETE_URL,
            {"confirm_email": verified_user.email, "password": "nope"},
            format="json",
        )
        assert response.status_code == 400
        verified_user.refresh_from_db()
        assert verified_user.is_active is True
        assert not AccountDeletionRequest.objects.exists()

    def test_oauth_only_user_needs_no_password(self, api_client, auth_as, db):
        user = User.objects.create_user(
            email="oauth-only@example.com", is_verified=True
        )
        user.set_unusable_password()
        user.save()
        auth_as(api_client, user)
        with _deletion_email_mock():
            response = api_client.post(
                DELETE_URL,
                {"confirm_email": user.email},
                format="json",
            )
        assert response.status_code == 202


class TestDeletionGraceWindow:
    def test_request_enters_grace_state(self, api_client, auth_as, verified_user):
        # A live session that must be revoked by the deletion request.
        JWTManager.create_token_pair(verified_user)
        assert RefreshToken.objects.filter(
            user=verified_user, is_revoked=False
        ).exists()

        auth_as(api_client, verified_user)
        before = timezone.now()
        with _deletion_email_mock() as send_confirmation:
            response = api_client.post(
                DELETE_URL,
                {"confirm_email": verified_user.email, "password": PASSWORD},
                format="json",
            )
        after = timezone.now()

        assert response.status_code == 202
        req = AccountDeletionRequest.objects.get(id=response.data["request_id"])
        assert req.status == AccountDeletionRequest.Status.PENDING
        assert req.user_id == verified_user.id
        assert req.user_email_snapshot == verified_user.email
        # 7-day grace window, measured against the request wall-clock.
        assert before + timedelta(days=7) <= req.scheduled_for
        assert req.scheduled_for <= after + timedelta(days=7)

        # Account is deactivated and every refresh token revoked.
        verified_user.refresh_from_db()
        assert verified_user.is_active is False
        assert not RefreshToken.objects.filter(
            user=verified_user, is_revoked=False
        ).exists()

        send_confirmation.assert_called_once()
        # Confirmation email gets a usable cancel token, not the JTI.
        assert send_confirmation.call_args.kwargs["cancel_token"]
        assert send_confirmation.call_args.kwargs["grace_days"] == 7

    def test_email_confirmation_is_case_insensitive(
        self, api_client, auth_as, verified_user
    ):
        auth_as(api_client, verified_user)
        with _deletion_email_mock():
            response = api_client.post(
                DELETE_URL,
                {
                    "confirm_email": verified_user.email.upper(),
                    "password": PASSWORD,
                },
                format="json",
            )
        assert response.status_code == 202

    def test_jwt_unusable_after_deletion_request(
        self, api_client, auth_as, verified_user
    ):
        auth_as(api_client, verified_user)
        with _deletion_email_mock():
            api_client.post(
                DELETE_URL,
                {"confirm_email": verified_user.email, "password": PASSWORD},
                format="json",
            )
        # Same Bearer token, user now inactive -> authentication fails.
        response = api_client.get(PROFILE_URL)
        assert response.status_code in (401, 403)

    def test_existing_pending_request_is_idempotent(
        self, api_client, auth_as, verified_user
    ):
        existing = AccountDeletionRequest.objects.create(
            user=verified_user,
            user_email_snapshot=verified_user.email,
            scheduled_for=timezone.now() + timedelta(days=5),
            cancel_token_jti="existing-jti-000",
        )
        auth_as(api_client, verified_user)
        with _deletion_email_mock() as send_confirmation:
            response = api_client.post(
                DELETE_URL,
                {"confirm_email": verified_user.email, "password": PASSWORD},
                format="json",
            )
        assert response.status_code == 202
        assert response.data["request_id"] == str(existing.id)
        assert AccountDeletionRequest.objects.count() == 1
        send_confirmation.assert_not_called()

    def test_email_send_failure_does_not_break_request(
        self, api_client, auth_as, verified_user
    ):
        auth_as(api_client, verified_user)
        with patch(
            "notifications.services.send_account_deletion_confirmation",
            side_effect=RuntimeError("smtp down"),
        ):
            response = api_client.post(
                DELETE_URL,
                {"confirm_email": verified_user.email, "password": PASSWORD},
                format="json",
            )
        assert response.status_code == 202
        assert AccountDeletionRequest.objects.filter(
            user=verified_user,
            status=AccountDeletionRequest.Status.PENDING,
        ).exists()


class TestDeletionCancel:
    def _make_request(self, user):
        return AccountDeletionRequest.objects.create(
            user=user,
            user_email_snapshot=user.email,
            scheduled_for=timezone.now() + timedelta(days=7),
            cancel_token_jti="cancel-jti-123",
        )

    def test_missing_token_rejected(self, api_client):
        response = api_client.post(CANCEL_URL, {}, format="json")
        assert response.status_code == 400

    def test_garbage_token_rejected(self, api_client):
        response = api_client.post(
            CANCEL_URL, {"token": "not-a-jwt"}, format="json"
        )
        assert response.status_code == 400

    def test_access_token_is_not_a_cancel_token(
        self, api_client, verified_user
    ):
        access = JWTManager.create_access_token(verified_user)
        response = api_client.post(CANCEL_URL, {"token": access}, format="json")
        assert response.status_code == 400

    def test_token_for_deleted_request_rejected(
        self, api_client, verified_user
    ):
        req = self._make_request(verified_user)
        token = create_cancel_deletion_token(req)
        req.delete()
        response = api_client.post(CANCEL_URL, {"token": token}, format="json")
        assert response.status_code == 400

    def test_valid_cancel_reactivates_account(self, api_client, verified_user):
        req = self._make_request(verified_user)
        verified_user.is_active = False
        verified_user.save(update_fields=["is_active"])
        token = create_cancel_deletion_token(req)

        response = api_client.post(CANCEL_URL, {"token": token}, format="json")

        assert response.status_code == 200
        req.refresh_from_db()
        assert req.status == AccountDeletionRequest.Status.CANCELED
        assert req.canceled_at is not None
        verified_user.refresh_from_db()
        assert verified_user.is_active is True

    def test_cancel_token_is_one_shot(self, api_client, verified_user):
        req = self._make_request(verified_user)
        verified_user.is_active = False
        verified_user.save(update_fields=["is_active"])
        token = create_cancel_deletion_token(req)

        first = api_client.post(CANCEL_URL, {"token": token}, format="json")
        assert first.status_code == 200
        # Re-use of the same token fails once the request is CANCELED.
        second = api_client.post(CANCEL_URL, {"token": token}, format="json")
        assert second.status_code == 400
        req.refresh_from_db()
        assert req.status == AccountDeletionRequest.Status.CANCELED


class TestHardDeleteCascadeSemantics:
    @pytest.fixture(autouse=True)
    def _billing_settings(self, settings):
        # override_settings can only decorate SimpleTestCase classes;
        # use the pytest-django settings fixture instead.
        settings.BILLING_ANONYMIZATION_PEPPER = TEST_PEPPER
        settings.STRIPE_SECRET_KEY = None

    def _pending_request(self, user, days_past=1):
        return AccountDeletionRequest.objects.create(
            user=user,
            user_email_snapshot=user.email,
            scheduled_for=timezone.now() - timedelta(days=days_past),
            cancel_token_jti=f"jti-{user.pk}",
        )

    def _usage_log(self, user, cost, month_start):
        log = UsageLog.objects.create(
            user=user,
            service="openrouter",
            feature="chat",
            cost_usd=Decimal(cost),
        )
        # timestamp is auto_now_add; move it into the target month.
        UsageLog.objects.filter(id=log.id).update(timestamp=month_start)
        return log

    def test_hard_delete_cascades_and_retains_anonymized_billing(
        self, verified_user
    ):
        uid = verified_user.id
        email = verified_user.email
        jan = timezone.now().replace(
            month=1, day=15, hour=12, minute=0, second=0, microsecond=0
        )
        feb = jan.replace(month=2)
        self._usage_log(verified_user, "1.25", jan)
        self._usage_log(verified_user, "0.75", jan)
        self._usage_log(verified_user, "2.00", feb)
        DataExportRequest.objects.create(user=verified_user)
        req = self._pending_request(verified_user)

        with _hard_delete_mocks() as (storage, send_email):
            result = hard_delete_account()

        assert result == {"deleted": 1, "failed": 0}

        # CASCADE: user and user-owned rows are gone.
        assert not User.objects.filter(id=uid).exists()
        assert not UsageLog.objects.filter(user_id=uid).exists()
        assert not DataExportRequest.objects.filter(user_id=uid).exists()

        # SET_NULL: the deletion-request row survives for audit,
        # detached from the user but keeping the email snapshot.
        req.refresh_from_db()
        assert req.user_id is None
        assert req.status == AccountDeletionRequest.Status.COMPLETED
        assert req.completed_at is not None
        assert req.user_email_snapshot == email

        # BillingSummary retention: HMAC token, monthly totals, no PII.
        token = anonymize_user_id(uid)
        summaries = BillingSummary.objects.filter(
            anonymized_user_token=token
        ).order_by("month")
        assert summaries.count() == 2
        jan_row, feb_row = summaries
        assert jan_row.month == jan.date().replace(day=1)
        assert jan_row.total_charged_usd == Decimal("2.0000")
        assert feb_row.total_charged_usd == Decimal("2.0000")
        for row in (jan_row, feb_row):
            assert str(uid) not in row.anonymized_user_token
            assert email not in row.anonymized_user_token
            assert email not in (row.country_code or "")

        send_email.assert_called_once()
        # Final email goes to the snapshot address (user row is gone).
        assert send_email.call_args.args[0] == email

    def test_set_null_in_memory_footgun_handled(self, verified_user):
        """After ``user.delete()`` the DB FK is NULL but the in-memory
        instance still points at the deleted user; the task must clear
        it before ``save(update_fields=[...])`` or the save raises.
        This asserts the round-trip completes and persists NULL."""
        req = self._pending_request(verified_user)
        with _hard_delete_mocks():
            result = hard_delete_account()
        assert result["failed"] == 0
        stored = AccountDeletionRequest.objects.get(id=req.id)
        assert stored.user is None

    def test_future_scheduled_request_is_untouched(self, verified_user):
        req = AccountDeletionRequest.objects.create(
            user=verified_user,
            user_email_snapshot=verified_user.email,
            scheduled_for=timezone.now() + timedelta(days=3),
            cancel_token_jti="future-jti",
        )
        with _hard_delete_mocks():
            result = hard_delete_account()
        assert result == {"deleted": 0, "failed": 0}
        req.refresh_from_db()
        assert req.status == AccountDeletionRequest.Status.PENDING
        assert User.objects.filter(id=verified_user.id).exists()

    def test_canceled_request_is_untouched(self, verified_user):
        AccountDeletionRequest.objects.create(
            user=verified_user,
            user_email_snapshot=verified_user.email,
            status=AccountDeletionRequest.Status.CANCELED,
            scheduled_for=timezone.now() - timedelta(days=1),
            cancel_token_jti="canceled-jti",
        )
        with _hard_delete_mocks():
            result = hard_delete_account()
        assert result == {"deleted": 0, "failed": 0}
        assert User.objects.filter(id=verified_user.id).exists()

    def test_failure_rolls_back_and_marks_failed(self, verified_user):
        self._usage_log(
            verified_user,
            "1.00",
            timezone.now().replace(day=1, hour=0, minute=0, second=0),
        )
        req = self._pending_request(verified_user)

        storage = MagicMock()
        storage.config.bucket_name = "test-bucket"
        storage._get_r2_client.side_effect = RuntimeError("R2 exploded")

        with _hard_delete_mocks(storage=storage):
            result = hard_delete_account()

        assert result == {"deleted": 0, "failed": 1}
        req.refresh_from_db()
        assert req.status == AccountDeletionRequest.Status.FAILED
        assert "R2 exploded" in req.failure_reason
        # Atomic rollback: user survives, nothing anonymized.
        assert User.objects.filter(id=verified_user.id).exists()
        assert BillingSummary.objects.count() == 0

    def test_pepper_must_be_configured(self, verified_user, settings):
        self._pending_request(verified_user)
        settings.BILLING_ANONYMIZATION_PEPPER = None
        with _hard_delete_mocks():
            result = hard_delete_account()
        # ImproperlyConfigured is caught per-request: marked FAILED,
        # user NOT deleted (refuses to corrupt tax aggregation).
        assert result == {"deleted": 0, "failed": 1}
        assert User.objects.filter(id=verified_user.id).exists()
