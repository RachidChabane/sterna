"""Celery tasks for daily R2 backup + health monitoring."""

import logging
from datetime import timedelta

from celery import shared_task
from django.core.cache import cache
from django.utils import timezone

logger = logging.getLogger(__name__)

LAST_SUCCESS_CACHE_KEY = "backup:r2:last_success"
LAST_SUCCESS_TIMEOUT = None  # never expire — overwritten on each success
STALE_THRESHOLD = timedelta(hours=30)


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=300,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=3600,
    time_limit=6 * 3600,
    soft_time_limit=int(5.5 * 3600),
    name="storage.tasks.backup_r2_user_assets",
)
def backup_r2_user_assets(self):
    """Daily task: copy user-assets bucket(s) to dated prefixes
    in the backup bucket, then sweep expired prefixes."""
    from storage.services import get_r2_backup_service

    svc = get_r2_backup_service()
    now = timezone.now()
    result = svc.run_daily_backup(now=now)
    sweep = svc.run_retention_sweep(now=now)

    logger.info(
        "r2_backup_run_complete",
        extra={
            "objects_copied": result.objects_copied,
            "objects_skipped": result.objects_skipped,
            "objects_failed": result.objects_failed,
            "bytes_copied": result.bytes_copied,
            "prefixes_deleted_total": sum(
                len(v) for v in sweep.deleted_prefixes.values()
            ),
            "objects_deleted": sweep.objects_deleted,
            "duration_seconds": (
                result.finished_at - result.started_at
            ).total_seconds(),
        },
    )

    # Heartbeat MUST be the last statement so any earlier exception
    # leaves the heartbeat stale.
    cache.set(LAST_SUCCESS_CACHE_KEY, now.isoformat(), timeout=None)
    return {
        "ok": True,
        "objects_copied": result.objects_copied,
        "objects_failed": result.objects_failed,
    }


@shared_task(name="storage.tasks.r2_backup_health_check")
def r2_backup_health_check():
    """Every 6 hours: if the last successful backup is older than
    30h, fire a Sentry error. If no backup has ever succeeded
    (heartbeat absent), skip silently — see plan §0.10."""
    now = timezone.now()
    last_iso = cache.get(LAST_SUCCESS_CACHE_KEY)
    if not last_iso:
        logger.warning("r2_backup_health_check no heartbeat yet, skipping")
        return {"ok": True, "skipped": "no_heartbeat"}

    last_success = timezone.datetime.fromisoformat(last_iso)
    age = now - last_success
    if age <= STALE_THRESHOLD:
        return {"ok": True, "age_seconds": age.total_seconds()}

    try:
        import sentry_sdk

        sentry_sdk.capture_message(
            "r2-backup-stale",
            level="error",
            fingerprint=["r2-backup-stale"],
            extras={
                "last_success": last_iso,
                "age_hours": age.total_seconds() / 3600,
                "threshold_hours": STALE_THRESHOLD.total_seconds() / 3600,
            },
        )
    except ImportError:
        pass
    logger.error(
        "r2_backup_stale",
        extra={
            "last_success": last_iso,
            "age_hours": age.total_seconds() / 3600,
        },
    )
    return {
        "ok": False,
        "stale": True,
        "age_seconds": age.total_seconds(),
    }
