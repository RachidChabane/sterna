"""GDPR Art. 15 — data export endpoint tests (task 16).

Covers:
- auth / verification requirements on both endpoints
- request flow: POST -> 202 -> eager Celery task -> READY status body
- in-progress and 24h-cooldown 429 guards
- ownership isolation (user A cannot read user B's export status)
- FAILED status body carries the failure reason

No real network: R2 storage is mocked and the export-ready email is
patched (``create=True`` because ``send_data_export_ready_email`` does
not exist yet in ``notifications.services`` — see the production-bug
note in the module docstring of ``test_gdpr_deletion``).
"""

from contextlib import contextmanager
from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest
from django.urls import reverse
from django.utils import timezone

from authentication.models import DataExportRequest, User

pytestmark = pytest.mark.django_db

EXPORT_URL = reverse("authentication:data-export-request")


def _status_url(request_id):
    return reverse(
        "authentication:data-export-status", kwargs={"request_id": request_id}
    )


@contextmanager
def _export_task_mocks():
    """Mock everything the eager ``export_user_data`` task touches.

    ``CELERY_TASK_ALWAYS_EAGER`` runs the task inline, so the R2
    storage service and the notification e-mail must both be stubbed.
    """
    storage = MagicMock()
    storage._upload_to_r2.return_value = True
    storage.config.bucket_name = "test-bucket"
    r2_client = storage._get_r2_client.return_value
    r2_client.generate_presigned_url.return_value = (
        "https://r2.example.test/user-exports/signed.zip"
    )
    with patch(
        "workspaces.services.workspace_storage.get_storage_service",
        return_value=storage,
    ), patch(
        "notifications.services.send_data_export_ready_email",
        create=True,
    ) as send_email:
        yield storage, send_email


class TestDataExportAuth:
    def test_anonymous_request_rejected(self, api_client):
        response = api_client.post(EXPORT_URL)
        assert response.status_code == 401

    def test_unverified_user_rejected(self, api_client, auth_as, db):
        user = User.objects.create_user(
            email="unverified@example.com",
            password="x-secret-1!",
            is_verified=False,
        )
        auth_as(api_client, user)
        response = api_client.post(EXPORT_URL)
        assert response.status_code == 403

    def test_anonymous_status_rejected(self, api_client, verified_user):
        req = DataExportRequest.objects.create(user=verified_user)
        response = api_client.get(_status_url(req.id))
        assert response.status_code == 401


class TestDataExportRequestFlow:
    def test_request_creates_export_and_completes_eagerly(
        self, api_client, auth_as, verified_user
    ):
        auth_as(api_client, verified_user)

        with _export_task_mocks() as (storage, send_email):
            response = api_client.post(EXPORT_URL)

        assert response.status_code == 202
        request_id = response.data["request_id"]

        req = DataExportRequest.objects.get(id=request_id, user=verified_user)
        # Celery is eager in tests: the task ran inline and finished.
        assert req.status == DataExportRequest.Status.READY
        assert req.download_url == (
            "https://r2.example.test/user-exports/signed.zip"
        )
        assert req.ready_at is not None
        assert req.download_url_expires_at == req.ready_at + timedelta(days=7)
        assert req.r2_key == f"user-exports/{verified_user.id}/{req.id}.zip"

        # The zip really was uploaded, and the ready email attempted.
        storage._upload_to_r2.assert_called_once()
        upload_key, upload_bytes, content_type = (
            storage._upload_to_r2.call_args.args
        )
        assert upload_key == req.r2_key
        assert content_type == "application/zip"
        assert upload_bytes[:2] == b"PK"  # zip magic
        send_email.assert_called_once()

    def test_status_endpoint_shows_ready_body(
        self, api_client, auth_as, verified_user
    ):
        auth_as(api_client, verified_user)
        with _export_task_mocks():
            request_id = api_client.post(EXPORT_URL).data["request_id"]

        response = api_client.get(_status_url(request_id))
        assert response.status_code == 200
        assert response.data["status"] == DataExportRequest.Status.READY
        assert response.data["download_url"].startswith("https://")
        assert response.data["expires_at"] is not None
        assert response.data["ready_at"] is not None

    def test_pending_export_blocks_second_request(
        self, api_client, auth_as, verified_user
    ):
        DataExportRequest.objects.create(
            user=verified_user, status=DataExportRequest.Status.PENDING
        )
        auth_as(api_client, verified_user)
        response = api_client.post(EXPORT_URL)
        assert response.status_code == 429
        assert "in progress" in response.data["error"]

    def test_processing_export_blocks_second_request(
        self, api_client, auth_as, verified_user
    ):
        DataExportRequest.objects.create(
            user=verified_user, status=DataExportRequest.Status.PROCESSING
        )
        auth_as(api_client, verified_user)
        response = api_client.post(EXPORT_URL)
        assert response.status_code == 429

    def test_recent_ready_export_enforces_24h_cooldown(
        self, api_client, auth_as, verified_user
    ):
        DataExportRequest.objects.create(
            user=verified_user,
            status=DataExportRequest.Status.READY,
            ready_at=timezone.now() - timedelta(hours=1),
        )
        auth_as(api_client, verified_user)
        response = api_client.post(EXPORT_URL)
        assert response.status_code == 429
        assert "24 hours" in response.data["error"]

    def test_stale_ready_export_allows_new_request(
        self, api_client, auth_as, verified_user
    ):
        DataExportRequest.objects.create(
            user=verified_user,
            status=DataExportRequest.Status.READY,
            ready_at=timezone.now() - timedelta(hours=25),
        )
        auth_as(api_client, verified_user)
        with _export_task_mocks():
            response = api_client.post(EXPORT_URL)
        assert response.status_code == 202

    def test_another_users_export_does_not_block(
        self, api_client, auth_as, verified_user, other_verified_user
    ):
        DataExportRequest.objects.create(
            user=other_verified_user,
            status=DataExportRequest.Status.PENDING,
        )
        auth_as(api_client, verified_user)
        with _export_task_mocks():
            response = api_client.post(EXPORT_URL)
        assert response.status_code == 202


class TestDataExportOwnershipIsolation:
    def test_user_cannot_read_other_users_export(
        self, api_client, auth_as, verified_user, other_verified_user
    ):
        others_req = DataExportRequest.objects.create(
            user=other_verified_user,
            status=DataExportRequest.Status.READY,
            ready_at=timezone.now(),
            download_url="https://r2.example.test/secret.zip",
        )
        auth_as(api_client, verified_user)
        response = api_client.get(_status_url(others_req.id))
        # Must be 404 (not 403): existence is not leaked either.
        assert response.status_code == 404
        assert "download_url" not in response.data

    def test_owner_can_read_own_export(
        self, api_client, auth_as, verified_user
    ):
        req = DataExportRequest.objects.create(user=verified_user)
        auth_as(api_client, verified_user)
        response = api_client.get(_status_url(req.id))
        assert response.status_code == 200
        assert response.data["request_id"] == str(req.id)
        assert response.data["status"] == DataExportRequest.Status.PENDING

    def test_unknown_export_id_is_404(self, api_client, auth_as, verified_user):
        auth_as(api_client, verified_user)
        response = api_client.get(
            _status_url("00000000-0000-0000-0000-000000000000")
        )
        assert response.status_code == 404


class TestDataExportFailureStates:
    def test_failed_export_status_carries_reason(
        self, api_client, auth_as, verified_user
    ):
        req = DataExportRequest.objects.create(
            user=verified_user,
            status=DataExportRequest.Status.FAILED,
            failed_reason="R2 upload failed",
        )
        auth_as(api_client, verified_user)
        response = api_client.get(_status_url(req.id))
        assert response.status_code == 200
        assert response.data["status"] == DataExportRequest.Status.FAILED
        assert response.data["error"] == "R2 upload failed"
        assert "download_url" not in response.data

    def test_upload_failure_marks_request_failed(
        self, api_client, auth_as, verified_user
    ):
        auth_as(api_client, verified_user)
        storage = MagicMock()
        storage._upload_to_r2.return_value = False  # upload refused
        storage.config.bucket_name = "test-bucket"
        with patch(
            "workspaces.services.workspace_storage.get_storage_service",
            return_value=storage,
        ), patch(
            "notifications.services.send_data_export_ready_email",
            create=True,
        ):
            # Eager Celery propagates the task's final exception after
            # its retries are exhausted; the row must still be FAILED.
            try:
                api_client.post(EXPORT_URL)
            except Exception:
                pass

        req = DataExportRequest.objects.filter(user=verified_user).latest(
            "requested_at"
        )
        assert req.status == DataExportRequest.Status.FAILED
        assert "upload" in req.failed_reason.lower()
