"""R2 backup service: copy user-assets bucket(s) to dated prefixes.

See docs/operations/r2-backup-restore.md for the operational runbook.
"""

import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone as dt_tz
from typing import Iterator, Optional

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)


class R2BackupPartialFailure(Exception):
    """Raised when per-object failure counts exceed the configured tolerance."""


@dataclass(frozen=True)
class BackupConfig:
    account_id: str
    access_key_id: str
    secret_access_key: str
    endpoint_url: str
    source_buckets: tuple[str, ...]
    dest_bucket: str
    max_object_bytes: int
    per_run_failure_tolerance: int
    per_run_failure_ratio: float
    ratio_floor: int = 200

    @classmethod
    def from_settings(cls) -> "BackupConfig":
        from django.conf import settings

        return cls(
            account_id=settings.R2_ACCOUNT_ID,
            access_key_id=settings.R2_ACCESS_KEY_ID,
            secret_access_key=settings.R2_SECRET_ACCESS_KEY,
            endpoint_url=(
                settings.R2_ENDPOINT_URL
                or f"https://{settings.R2_ACCOUNT_ID}.r2.cloudflarestorage.com"
            ),
            source_buckets=tuple(settings.R2_BACKUP_SOURCE_BUCKETS),
            dest_bucket=settings.R2_BACKUP_DEST_BUCKET,
            max_object_bytes=settings.R2_BACKUP_MAX_OBJECT_BYTES,
            per_run_failure_tolerance=settings.R2_BACKUP_PER_RUN_TOLERANCE,
            per_run_failure_ratio=settings.R2_BACKUP_PER_RUN_FAILURE_RATIO,
            ratio_floor=settings.R2_BACKUP_RATIO_FLOOR,
        )


@dataclass
class BackupRunResult:
    started_at: datetime
    finished_at: datetime
    objects_copied: int
    objects_skipped: int
    objects_failed: int
    bytes_copied: int
    failed_keys: list[tuple[str, str]] = field(default_factory=list)


@dataclass
class RetentionSweepResult:
    deleted_prefixes: dict[str, list[str]]
    objects_deleted: int


@dataclass
class CopyResult:
    skipped: bool
    bytes: int
    error: Optional[str] = None


class R2BackupService:
    """Copy R2 source buckets to dated prefixes in the backup bucket."""

    def __init__(self, config: Optional[BackupConfig] = None):
        self.config = config or BackupConfig.from_settings()
        self._client = None
        self._client_lock = threading.Lock()

    @property
    def client(self):
        return self._get_client()

    def _get_client(self):
        if self._client is not None:
            return self._client
        with self._client_lock:
            if self._client is not None:
                return self._client
            self._client = boto3.client(
                "s3",
                endpoint_url=self.config.endpoint_url,
                aws_access_key_id=self.config.access_key_id,
                aws_secret_access_key=self.config.secret_access_key,
                config=Config(
                    signature_version="s3v4",
                    retries={"max_attempts": 3, "mode": "adaptive"},
                ),
            )
            return self._client

    # ─── main entry points ───

    def run_daily_backup(
        self, now: Optional[datetime] = None
    ) -> BackupRunResult:
        now = now or datetime.now(dt_tz.utc)
        try:
            return self._run_daily_backup_impl(now)
        except Exception as exc:
            try:
                import sentry_sdk

                sentry_sdk.capture_exception(
                    exc, fingerprint=["r2-backup-run-failed"]
                )
            except ImportError:
                pass
            raise

    def _run_daily_backup_impl(self, now: datetime) -> BackupRunResult:
        prefixes = self.date_prefixes_for(now)
        result = BackupRunResult(
            started_at=now,
            finished_at=now,
            objects_copied=0,
            objects_skipped=0,
            objects_failed=0,
            bytes_copied=0,
            failed_keys=[],
        )
        total_attempts = 0
        for src_bucket in self.config.source_buckets:
            for obj in self._list_source_objects(src_bucket):
                size = obj["Size"]
                key = obj["Key"]
                if size > self.config.max_object_bytes:
                    logger.warning(
                        "r2_backup_skip_oversize bucket=%s key=%s size=%d cap=%d",
                        src_bucket,
                        key,
                        size,
                        self.config.max_object_bytes,
                    )
                    result.objects_skipped += 1
                    continue
                for prefix in prefixes:
                    total_attempts += 1
                    dest_key = f"{prefix}{src_bucket}/{key}"
                    try:
                        cr = self._copy_one(
                            src_bucket, key, size, dest_key
                        )
                    except ClientError as exc:
                        result.objects_failed += 1
                        result.failed_keys.append((src_bucket, key))
                        logger.warning(
                            "r2_backup_copy_failed bucket=%s key=%s dest=%s error=%s",
                            src_bucket,
                            key,
                            dest_key,
                            exc,
                        )
                        continue
                    if cr.skipped:
                        result.objects_skipped += 1
                    else:
                        result.objects_copied += 1
                        result.bytes_copied += cr.bytes
        if total_attempts > 0:
            tolerance = self.config.per_run_failure_tolerance
            ratio_limit = self.config.per_run_failure_ratio
            ratio_floor = self.config.ratio_floor
            absolute_trips = result.objects_failed > tolerance
            ratio_trips = (
                total_attempts >= ratio_floor
                and result.objects_failed / total_attempts > ratio_limit
            )
            if absolute_trips or ratio_trips:
                raise R2BackupPartialFailure(
                    f"{result.objects_failed}/{total_attempts} copies failed "
                    f"(tolerance={tolerance}, ratio_limit={ratio_limit}, "
                    f"ratio_floor={ratio_floor})"
                )
        if result.failed_keys:
            logger.warning(
                "r2_backup_failed_keys_summary count=%d keys=%s",
                len(result.failed_keys),
                result.failed_keys,
            )
        result.finished_at = datetime.now(dt_tz.utc)
        return result

    def run_retention_sweep(
        self, now: Optional[datetime] = None
    ) -> RetentionSweepResult:
        now = now or datetime.now(dt_tz.utc)
        deleted: dict[str, list[str]] = {
            "daily": [],
            "weekly": [],
            "monthly": [],
        }
        objects_deleted = 0
        for kind in ("daily", "weekly", "monthly"):
            top_prefix = f"r2/{kind}/"
            for segment in self._list_date_segments(top_prefix):
                prefix = f"{top_prefix}{segment}/"
                if self.is_expired(prefix, now, kind):
                    n = self._delete_prefix(prefix)
                    deleted[kind].append(prefix)
                    objects_deleted += n
        return RetentionSweepResult(
            deleted_prefixes=deleted, objects_deleted=objects_deleted
        )

    # ─── helpers (public for testability) ───

    @staticmethod
    def date_prefixes_for(now: datetime) -> list[str]:
        """Return dest prefixes to write today: always daily, plus
        weekly on Sunday and monthly on day-1."""
        prefixes = [f"r2/daily/{now.strftime('%Y-%m-%d')}/"]
        iso_year, iso_week, iso_weekday = now.isocalendar()
        if iso_weekday == 7:
            prefixes.append(f"r2/weekly/{iso_year}-W{iso_week:02d}/")
        if now.day == 1:
            prefixes.append(f"r2/monthly/{now.strftime('%Y-%m')}/")
        return prefixes

    @staticmethod
    def is_expired(prefix: str, now: datetime, kind: str) -> bool:
        # prefix is "r2/<kind>/<date>/" — date segment is the third part.
        parts = prefix.strip("/").split("/")
        if len(parts) < 3:
            return False
        date_segment = parts[2]
        today = now.date()
        if kind == "daily":
            try:
                d = datetime.strptime(date_segment, "%Y-%m-%d").date()
            except ValueError:
                return False
            return (today - d).days > 30
        if kind == "weekly":
            try:
                year_part, week_part = date_segment.split("-W")
                monday = datetime.fromisocalendar(
                    int(year_part), int(week_part), 1
                ).date()
            except (ValueError, TypeError):
                return False
            return (today - monday).days > 12 * 7
        if kind == "monthly":
            try:
                d = datetime.strptime(date_segment, "%Y-%m").date()
            except ValueError:
                return False
            return (today - d).days > 365
        return False

    # ─── internal helpers ───

    def _list_source_objects(self, bucket: str) -> Iterator[dict]:
        paginator = self._get_client().get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=bucket):
            for obj in page.get("Contents") or []:
                yield obj

    def _list_date_segments(self, top_prefix: str) -> list[str]:
        client = self._get_client()
        seen: set[str] = set()
        paginator = client.get_paginator("list_objects_v2")
        for page in paginator.paginate(
            Bucket=self.config.dest_bucket,
            Prefix=top_prefix,
            Delimiter="/",
        ):
            for cp in page.get("CommonPrefixes") or []:
                cp_prefix = cp["Prefix"]
                segment = cp_prefix[len(top_prefix):].rstrip("/")
                if segment:
                    seen.add(segment)
        return sorted(seen)

    def _copy_one(
        self,
        src_bucket: str,
        src_key: str,
        src_size: int,
        dest_key: str,
    ) -> CopyResult:
        client = self._get_client()
        try:
            existing = client.head_object(
                Bucket=self.config.dest_bucket, Key=dest_key
            )
            if existing.get("ContentLength") == src_size:
                return CopyResult(skipped=True, bytes=0)
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            if code not in ("404", "NoSuchKey", "NotFound"):
                raise
        client.copy_object(
            Bucket=self.config.dest_bucket,
            Key=dest_key,
            CopySource={"Bucket": src_bucket, "Key": src_key},
        )
        return CopyResult(skipped=False, bytes=src_size)

    def _delete_prefix(self, prefix: str) -> int:
        client = self._get_client()
        deleted = 0
        paginator = client.get_paginator("list_objects_v2")
        for page in paginator.paginate(
            Bucket=self.config.dest_bucket, Prefix=prefix
        ):
            objects = page.get("Contents") or []
            if not objects:
                continue
            client.delete_objects(
                Bucket=self.config.dest_bucket,
                Delete={
                    "Objects": [{"Key": o["Key"]} for o in objects],
                    "Quiet": True,
                },
            )
            deleted += len(objects)
        return deleted


_instance: Optional[R2BackupService] = None
_lock = threading.Lock()


def get_r2_backup_service() -> R2BackupService:
    global _instance
    with _lock:
        if _instance is None:
            _instance = R2BackupService()
        return _instance
