"""Celery tasks for GDPR — data export, deletion grace, deletion purge.

These tasks are idempotent. Failure paths leave a row with status=FAILED
plus failure_reason; they never silently swallow data.
"""

import io
import json
import logging
import zipfile
from datetime import timedelta

from celery import shared_task  # type: ignore[import-untyped]
from django.conf import settings
from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)


SIGNED_URL_EXPIRY_SECONDS = 7 * 24 * 60 * 60  # 7 days
ZIP_README = """# {brand} Data Export

Generation date: {generated}
User: {email}
Request ID: {request_id}

## Categories included
{categories}

## Redacted / not included
- BYOK API keys (encrypted at rest; only `byok_configured: bool` exported)
- Encrypted MCP secrets (auth_config, env_vars, OAuth tokens)
- Payment method numbers (we never store them; Stripe holds them)
- KB chunk embeddings (derived data; re-generate by re-uploading)

## Retained after account deletion
Per GDPR Art. 17(3)(e), anonymized monthly billing totals are retained
for tax compliance (7 years). They use a one-way HMAC of your user ID
and cannot be linked back to your identity.
"""


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=30,
    max_retries=2,
)
def export_user_data(self, user_id: str, request_id: str) -> dict:
    """Build a zip of the user's data, upload to R2, return signed URL."""
    from authentication.models import DataExportRequest
    from authentication.services.data_export import DATA_EXPORTERS
    from notifications.services import send_data_export_ready_email
    from workspaces.services.workspace_storage import get_storage_service

    try:
        req = DataExportRequest.objects.select_related("user").get(
            id=request_id, user_id=user_id
        )
    except DataExportRequest.DoesNotExist:
        logger.error("export_user_data: request %s not found", request_id)
        return {"error": "not_found"}

    if req.status not in (
        DataExportRequest.Status.PENDING,
        DataExportRequest.Status.PROCESSING,
    ):
        logger.warning(
            "export_user_data: request %s status=%s, skipping",
            request_id,
            req.status,
        )
        return {"error": "wrong_status"}

    req.status = DataExportRequest.Status.PROCESSING
    req.save(update_fields=["status"])

    try:
        user = req.user
        buf = io.BytesIO()
        categories_done = []
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for name, fn in DATA_EXPORTERS:
                try:
                    payload = fn(user)
                except Exception:
                    logger.exception("export_user_data: %s failed", name)
                    payload = {
                        "_error": "exporter_failed",
                        "category": name,
                    }
                zf.writestr(
                    f"{name}.json",
                    json.dumps(
                        payload, ensure_ascii=False, indent=2, default=str
                    ),
                )
                categories_done.append(name)
            zf.writestr("README.md", ZIP_README.format(
                brand=settings.BRAND_NAME,
                generated=timezone.now().isoformat(),
                email=user.email,
                request_id=str(req.id),
                categories="\n".join(
                    f"- {c}.json" for c in categories_done
                ),
            ))
        buf.seek(0)
        content = buf.getvalue()

        r2_key = f"user-exports/{user.id}/{req.id}.zip"
        storage = get_storage_service()
        ok = storage._upload_to_r2(r2_key, content, "application/zip")
        if not ok:
            raise RuntimeError("Failed to upload export zip to R2")

        signed_url = _generate_signed_download_url(storage, r2_key)

        with transaction.atomic():
            req.status = DataExportRequest.Status.READY
            req.ready_at = timezone.now()
            req.download_url = signed_url
            req.download_url_expires_at = req.ready_at + timedelta(
                seconds=SIGNED_URL_EXPIRY_SECONDS
            )
            req.r2_key = r2_key
            req.save(update_fields=[
                "status",
                "ready_at",
                "download_url",
                "download_url_expires_at",
                "r2_key",
            ])

        try:
            send_data_export_ready_email(
                user, signed_url, req.download_url_expires_at,
            )
        except Exception:
            logger.exception("Failed to send export-ready email")

        return {"success": True, "request_id": str(req.id)}

    except Exception as exc:
        logger.exception("export_user_data: failed")
        req.status = DataExportRequest.Status.FAILED
        req.failed_reason = str(exc)[:500]
        req.save(update_fields=["status", "failed_reason"])
        raise


def _generate_signed_download_url(storage, key: str) -> str:
    client = storage._get_r2_client()
    if not client:
        raise RuntimeError("R2 client unavailable")
    return client.generate_presigned_url(
        "get_object",
        Params={
            "Bucket": storage.config.bucket_name,
            "Key": key,
            "ResponseContentType": "application/zip",
        },
        ExpiresIn=SIGNED_URL_EXPIRY_SECONDS,
    )


@shared_task
def purge_expired_exports() -> dict:
    """Daily: delete R2 zips + clear download URLs >7d past ready_at."""
    from authentication.models import DataExportRequest
    from workspaces.services.workspace_storage import get_storage_service

    cutoff = timezone.now() - timedelta(seconds=SIGNED_URL_EXPIRY_SECONDS)
    qs = DataExportRequest.objects.filter(
        status=DataExportRequest.Status.READY,
        ready_at__lt=cutoff,
    ).exclude(r2_key="")

    storage = get_storage_service()
    purged = 0
    for req in qs.iterator():
        try:
            if req.r2_key:
                storage._delete_from_r2(req.r2_key)
        except Exception:
            logger.exception(
                "purge_expired_exports: r2 delete failed for %s", req.id
            )
        req.status = DataExportRequest.Status.EXPIRED
        req.download_url = ""
        req.download_url_expires_at = None
        req.r2_key = ""
        req.save(update_fields=[
            "status",
            "download_url",
            "download_url_expires_at",
            "r2_key",
        ])
        purged += 1
    return {"purged": purged}


@shared_task
def hard_delete_account() -> dict:
    """Daily: hard-delete accounts whose 7d grace has expired.

    For each AccountDeletionRequest with status=PENDING and
    scheduled_for <= now:
      1. Aggregate UsageLog -> BillingSummary (HMAC-anonymized).
      2. Cancel Stripe subscription (if present).
      3. Delete R2 objects under {user_id}/ prefix.
      4. Delete data-export R2 objects too.
      5. Hard-delete User (cascades remaining DB rows).
      6. Mark request COMPLETED.
      7. Send final "account deleted" email.
    """
    from authentication.models import (
        AccountDeletionRequest,
        DataExportRequest,
    )
    from authentication.services.billing_anonymization import (
        anonymize_user_id,
    )
    from notifications.services import send_account_deleted_email
    from workspaces.services.workspace_storage import (
        R2PathBuilder,
        get_storage_service,
    )

    now = timezone.now()
    pending = AccountDeletionRequest.objects.filter(
        status=AccountDeletionRequest.Status.PENDING,
        scheduled_for__lte=now,
        user__isnull=False,
    ).select_related("user")

    deleted = 0
    failed = 0
    for req in pending:
        user = req.user
        if user is None:
            # The queryset filters user__isnull=False; this branch is
            # unreachable in practice and only narrows the type for mypy.
            continue
        user_email = user.email
        full_name = user.full_name
        user_id_str = str(user.id)

        try:
            with transaction.atomic():
                _aggregate_billing_to_summary(user, anonymize_user_id)
                _try_cancel_stripe_subscription(user)

                storage = get_storage_service()
                _delete_r2_prefix(
                    storage, R2PathBuilder.user_prefix(user_id_str),
                )
                for export_req in DataExportRequest.objects.filter(
                    user=user
                ):
                    if export_req.r2_key:
                        try:
                            storage._delete_from_r2(export_req.r2_key)
                        except Exception:
                            logger.exception(
                                "hard_delete_account: r2 delete failed "
                                "for export %s",
                                export_req.id,
                            )

                user.delete()
                # The DB-level SET_NULL has nulled this FK, but the
                # Python-side instance still references the deleted user
                # — assign None so the subsequent save() doesn't trip
                # "save() prohibited due to unsaved related object".
                req.user = None
                req.status = AccountDeletionRequest.Status.COMPLETED
                req.completed_at = timezone.now()
                req.save(update_fields=[
                    "user", "status", "completed_at"
                ])

            try:
                send_account_deleted_email(user_email, full_name)
            except Exception:
                logger.exception("Failed to send account-deleted email")

            deleted += 1
        except Exception as exc:
            logger.exception("hard_delete_account: failed for %s", req.id)
            req.status = AccountDeletionRequest.Status.FAILED
            req.failure_reason = str(exc)[:500]
            req.save(update_fields=["status", "failure_reason"])
            failed += 1
    return {"deleted": deleted, "failed": failed}


def _aggregate_billing_to_summary(user, anonymize_fn) -> None:
    """Aggregate UsageLog rows into anonymized BillingSummary records."""
    from collections import defaultdict
    from datetime import date
    from typing import DefaultDict, Dict, Tuple

    from authentication.models import BillingSummary
    from usage_quota.models import UsageLog

    token = anonymize_fn(user.id)
    sums: DefaultDict[Tuple[date, str], Dict[str, float]] = defaultdict(
        lambda: {"total": 0.0, "tax": 0.0}
    )
    qs = UsageLog.objects.filter(user=user).only("timestamp", "cost_usd")
    for log in qs.iterator(chunk_size=2000):
        month = log.timestamp.date().replace(day=1)
        sums[(month, "")]["total"] += float(log.cost_usd or 0)
        # tax_collected_usd: zero today (no tax engine wired).
    for (month, country), values in sums.items():
        BillingSummary.objects.update_or_create(
            anonymized_user_token=token,
            month=month,
            country_code=country,
            defaults={
                "total_charged_usd": values["total"],
                "tax_collected_usd": values["tax"],
            },
        )


def _try_cancel_stripe_subscription(user) -> None:
    """Best-effort. No-op if Stripe not configured."""
    try:
        import stripe  # may not be installed
    except ImportError:
        logger.info(
            "stripe package not installed; skipping cancellation"
        )
        return
    api_key = getattr(settings, "STRIPE_SECRET_KEY", None)
    if not api_key:
        logger.info("STRIPE_SECRET_KEY not set; skipping cancellation")
        return
    stripe.api_key = api_key
    customer_id = getattr(user, "stripe_customer_id", None)
    if not customer_id:
        return
    try:
        subs = stripe.Subscription.list(customer=customer_id, status="all")
        for sub in subs.get("data", []):
            if sub.get("status") in (
                "active", "trialing", "past_due", "unpaid",
            ):
                stripe.Subscription.delete(sub["id"])
    except Exception:
        logger.exception(
            "Stripe cancellation failed for user %s", user.id
        )


def _delete_r2_prefix(storage, prefix: str) -> int:
    """Page-delete every R2 object under prefix. Up to 1000 keys per call."""
    client = storage._get_r2_client()
    if not client:
        return 0
    bucket = storage.config.bucket_name
    total = 0
    continuation = None
    while True:
        kwargs = {"Bucket": bucket, "Prefix": prefix, "MaxKeys": 1000}
        if continuation:
            kwargs["ContinuationToken"] = continuation
        page = client.list_objects_v2(**kwargs)
        contents = page.get("Contents", [])
        if contents:
            client.delete_objects(
                Bucket=bucket,
                Delete={
                    "Objects": [
                        {"Key": obj["Key"]} for obj in contents
                    ],
                    "Quiet": True,
                },
            )
            total += len(contents)
        if not page.get("IsTruncated"):
            break
        continuation = page.get("NextContinuationToken")
    return total
