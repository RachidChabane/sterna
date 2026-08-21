"""Quota-exceeded rejections must leave an AuditLog trail.

The DRF exception handler (sterna.exceptions.billing_exception_handler)
is the single choke point every QuotaExceededException flows through, so
the audit record is written there.
"""

from decimal import Decimal

import pytest
from django.test import RequestFactory

from audit_logging.models import AuditLog
from sterna.exceptions import billing_exception_handler
from usage_quota.exceptions import QuotaExceededException


def _quota_exc(**overrides):
    kwargs = dict(
        message="Weekly quota exceeded",
        limit_usd=Decimal("10.00"),
        used_usd=Decimal("10.50"),
        remaining_usd=Decimal("0.00"),
        limit_type="weekly",
        feature_name="chat",
    )
    kwargs.update(overrides)
    return QuotaExceededException(**kwargs)


def _request(user=None, request_id="rid-quota-1"):
    req = RequestFactory().post("/api/llm/chat/")
    req.request_id = request_id
    if user is not None:
        req.user = user
    return req


@pytest.mark.django_db
class TestQuotaExceededAudit:
    def test_audit_log_written_on_quota_exceeded(self):
        response = billing_exception_handler(
            _quota_exc(), {"request": _request()},
        )
        assert response.status_code == 402

        entry = AuditLog.objects.get(action="BILLING_QUOTA_EXCEEDED")
        assert entry.request_id == "rid-quota-1"
        assert entry.success is False
        assert entry.extra_data["limit_type"] == "weekly"
        assert entry.extra_data["feature"] == "chat"

    def test_audit_log_records_authenticated_user(self):
        from django.contrib.auth import get_user_model

        user = get_user_model().objects.create_user(
            email="quota-audit@example.com", password="x-test-pass-1",
        )
        billing_exception_handler(
            _quota_exc(limit_type="monthly"),
            {"request": _request(user=user)},
        )
        entry = AuditLog.objects.get(action="BILLING_QUOTA_EXCEEDED")
        assert entry.user_id == user.id
        assert entry.extra_data["limit_type"] == "monthly"

    def test_audit_failure_does_not_break_402(self, monkeypatch):
        """The audit write is best-effort: a DB hiccup must never turn
        a 402 into a 500."""
        from audit_logging.models import AuditLog as _AL

        def _boom(**kwargs):
            raise RuntimeError("db down")

        monkeypatch.setattr(_AL.objects, "log", _boom)
        response = billing_exception_handler(
            _quota_exc(), {"request": _request()},
        )
        assert response.status_code == 402
        assert AuditLog.objects.count() == 0

    def test_no_audit_for_other_exceptions(self):
        response = billing_exception_handler(
            ValueError("unrelated"), {"request": _request()},
        )
        # DRF's default handler returns None for non-API exceptions.
        assert response is None
        assert AuditLog.objects.count() == 0
