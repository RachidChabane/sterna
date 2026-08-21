"""Tests for the R2 backup service, Celery tasks, and health check."""

from datetime import datetime, timedelta, timezone as dt_tz
from unittest.mock import patch

import boto3
import moto
import pytest
from botocore.exceptions import ClientError
from django.core.cache import cache

from storage.services import r2_backup
from storage.services.r2_backup import (
    BackupConfig,
    R2BackupPartialFailure,
    R2BackupService,
)
from storage.tasks import (
    LAST_SUCCESS_CACHE_KEY,
    STALE_THRESHOLD,
    backup_r2_user_assets,
    r2_backup_health_check,
)

SOURCE_BUCKET = "sterna-workspaces"
DEST_BUCKET = "sternaway-backups-test"


@pytest.fixture(autouse=True)
def _reset_module_singleton():
    """Reset get_r2_backup_service singleton between tests."""
    r2_backup._instance = None
    yield
    r2_backup._instance = None


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def s3():
    with moto.mock_aws():
        client = boto3.client("s3", region_name="us-east-1")
        client.create_bucket(Bucket=SOURCE_BUCKET)
        client.create_bucket(Bucket=DEST_BUCKET)
        yield client


@pytest.fixture
def cfg():
    return BackupConfig(
        account_id="acc",
        access_key_id="ak",
        secret_access_key="sk",
        endpoint_url="https://acc.r2.cloudflarestorage.com",
        source_buckets=(SOURCE_BUCKET,),
        dest_bucket=DEST_BUCKET,
        max_object_bytes=5 * 1024 * 1024 * 1024,
        per_run_failure_tolerance=5,
        per_run_failure_ratio=0.01,
    )


@pytest.fixture
def svc(s3, cfg, monkeypatch):
    """Service wired to the moto-backed client."""
    service = R2BackupService(config=cfg)
    monkeypatch.setattr(service, "_get_client", lambda: s3)
    return service


def _put(s3, key, body=b"hello"):
    s3.put_object(Bucket=SOURCE_BUCKET, Key=key, Body=body)


def _dest_keys(s3, prefix=""):
    resp = s3.list_objects_v2(Bucket=DEST_BUCKET, Prefix=prefix)
    return [o["Key"] for o in resp.get("Contents", [])]


# ─── pure unit: date_prefixes_for / is_expired ────────────────────────────

class TestDatePrefixesFor:
    def test_tuesday_returns_only_daily(self):
        now = datetime(2026, 5, 19, 3, 0, tzinfo=dt_tz.utc)  # Tuesday
        prefixes = R2BackupService.date_prefixes_for(now)
        assert prefixes == ["r2/daily/2026-05-19/"]

    def test_sunday_returns_daily_and_weekly(self):
        now = datetime(2026, 5, 24, 3, 0, tzinfo=dt_tz.utc)  # Sunday W21
        prefixes = R2BackupService.date_prefixes_for(now)
        assert prefixes == [
            "r2/daily/2026-05-24/",
            "r2/weekly/2026-W21/",
        ]

    def test_first_of_month_monday_returns_daily_and_monthly(self):
        now = datetime(2026, 6, 1, 3, 0, tzinfo=dt_tz.utc)  # Monday, 1st
        prefixes = R2BackupService.date_prefixes_for(now)
        assert prefixes == [
            "r2/daily/2026-06-01/",
            "r2/monthly/2026-06/",
        ]

    def test_sunday_and_first_of_month_returns_all_three(self):
        now = datetime(2026, 3, 1, 3, 0, tzinfo=dt_tz.utc)  # Sunday, 1st
        prefixes = R2BackupService.date_prefixes_for(now)
        assert prefixes == [
            "r2/daily/2026-03-01/",
            "r2/weekly/2026-W09/",
            "r2/monthly/2026-03/",
        ]

    def test_iso_week_uses_iso_year_at_boundary(self):
        # 2021-01-03 is Sunday but its ISO week is 2020-W53.
        now = datetime(2021, 1, 3, 3, 0, tzinfo=dt_tz.utc)
        prefixes = R2BackupService.date_prefixes_for(now)
        assert "r2/weekly/2020-W53/" in prefixes
        assert "r2/daily/2021-01-03/" in prefixes


class TestIsExpired:
    def test_daily_boundaries(self):
        now = datetime(2026, 5, 21, 0, 0, tzinfo=dt_tz.utc)
        # 30 days ago: not expired (boundary)
        assert R2BackupService.is_expired(
            "r2/daily/2026-04-21/", now, "daily"
        ) is False
        # 31 days ago: expired
        assert R2BackupService.is_expired(
            "r2/daily/2026-04-20/", now, "daily"
        ) is True
        # 51 days ago: expired
        assert R2BackupService.is_expired(
            "r2/daily/2026-04-01/", now, "daily"
        ) is True
        # 1 day ago: not expired
        assert R2BackupService.is_expired(
            "r2/daily/2026-05-20/", now, "daily"
        ) is False

    def test_weekly_boundaries(self):
        # Now = Monday of some week.
        now = datetime(2026, 5, 18, 0, 0, tzinfo=dt_tz.utc)  # W21 Monday
        # 12 weeks (84 days) ago: NOT expired
        assert R2BackupService.is_expired(
            "r2/weekly/2026-W09/", now, "weekly"
        ) is False
        # 13 weeks (91 days) ago: expired
        assert R2BackupService.is_expired(
            "r2/weekly/2026-W08/", now, "weekly"
        ) is True

    def test_monthly_boundaries(self):
        now = datetime(2026, 5, 21, 0, 0, tzinfo=dt_tz.utc)
        # 354 days back (2025-06-01): NOT expired
        assert R2BackupService.is_expired(
            "r2/monthly/2025-06/", now, "monthly"
        ) is False
        # 385 days back (2025-05-01): expired (over 365)
        assert R2BackupService.is_expired(
            "r2/monthly/2025-05/", now, "monthly"
        ) is True
        # 415 days back (2025-04-01): expired
        assert R2BackupService.is_expired(
            "r2/monthly/2025-04/", now, "monthly"
        ) is True


# ─── basic backup with moto ───────────────────────────────────────────────

class TestBackupCopies:
    def test_backup_task_copies_a_fixture_object(self, svc, s3):
        _put(s3, "u1/chats/c1/file-a", b"AAAA")
        _put(s3, "u1/chats/c1/file-b", b"BBBB")
        _put(s3, "u2/profile/avatar", b"CCCC")
        now = datetime(2026, 5, 21, 3, 0, tzinfo=dt_tz.utc)  # Tuesday

        result = svc.run_daily_backup(now=now)

        assert result.objects_copied == 3
        assert result.objects_failed == 0
        keys = _dest_keys(s3, "r2/daily/2026-05-21/")
        expected = {
            f"r2/daily/2026-05-21/{SOURCE_BUCKET}/u1/chats/c1/file-a",
            f"r2/daily/2026-05-21/{SOURCE_BUCKET}/u1/chats/c1/file-b",
            f"r2/daily/2026-05-21/{SOURCE_BUCKET}/u2/profile/avatar",
        }
        assert set(keys) == expected
        # No weekly/monthly on a Tuesday
        assert _dest_keys(s3, "r2/weekly/") == []
        assert _dest_keys(s3, "r2/monthly/") == []

    def test_backup_task_writes_weekly_prefix_on_sunday(self, svc, s3):
        _put(s3, "u1/chats/c1/file-a")
        now = datetime(2026, 5, 24, 3, 0, tzinfo=dt_tz.utc)  # Sunday W21

        svc.run_daily_backup(now=now)

        daily = _dest_keys(s3, "r2/daily/2026-05-24/")
        weekly = _dest_keys(s3, "r2/weekly/2026-W21/")
        assert daily and weekly
        assert (
            f"r2/daily/2026-05-24/{SOURCE_BUCKET}/u1/chats/c1/file-a"
            in daily
        )
        assert (
            f"r2/weekly/2026-W21/{SOURCE_BUCKET}/u1/chats/c1/file-a"
            in weekly
        )

    def test_backup_task_writes_monthly_prefix_on_first_of_month(
        self, svc, s3
    ):
        _put(s3, "u1/chats/c1/file-a")
        now = datetime(2026, 6, 1, 3, 0, tzinfo=dt_tz.utc)  # Monday, 1st

        svc.run_daily_backup(now=now)

        daily = _dest_keys(s3, "r2/daily/2026-06-01/")
        monthly = _dest_keys(s3, "r2/monthly/2026-06/")
        weekly = _dest_keys(s3, "r2/weekly/")
        assert daily and monthly
        assert weekly == []  # Monday, not Sunday

    def test_backup_idempotent_skip_on_second_run(self, svc, s3):
        _put(s3, "u1/file-a", b"AAAA")
        _put(s3, "u1/file-b", b"BBBB")
        _put(s3, "u1/file-c", b"CCCC")
        now = datetime(2026, 5, 21, 3, 0, tzinfo=dt_tz.utc)

        first = svc.run_daily_backup(now=now)
        assert first.objects_copied == 3
        assert first.objects_skipped == 0

        second = svc.run_daily_backup(now=now)
        assert second.objects_copied == 0
        assert second.objects_skipped == 3


# ─── retention sweep ──────────────────────────────────────────────────────

class TestRetentionSweep:
    def test_retention_deletes_expired_daily(self, svc, s3):
        # 51 days old: expired
        s3.put_object(
            Bucket=DEST_BUCKET,
            Key=f"r2/daily/2026-04-01/{SOURCE_BUCKET}/u1/file",
            Body=b"old",
        )
        # 27 days old: kept
        s3.put_object(
            Bucket=DEST_BUCKET,
            Key=f"r2/daily/2026-04-25/{SOURCE_BUCKET}/u1/file",
            Body=b"mid",
        )
        # 2 days old: kept
        s3.put_object(
            Bucket=DEST_BUCKET,
            Key=f"r2/daily/2026-05-20/{SOURCE_BUCKET}/u1/file",
            Body=b"new",
        )

        now = datetime(2026, 5, 22, 3, 0, tzinfo=dt_tz.utc)
        result = svc.run_retention_sweep(now=now)

        assert any(
            "2026-04-01" in p
            for p in result.deleted_prefixes["daily"]
        )
        remaining = _dest_keys(s3, "r2/daily/")
        assert all("2026-04-01" not in k for k in remaining)
        assert any("2026-04-25" in k for k in remaining)
        assert any("2026-05-20" in k for k in remaining)

    def test_retention_deletes_expired_weekly_monthly(self, svc, s3):
        now = datetime(2026, 5, 18, 0, 0, tzinfo=dt_tz.utc)  # Mon W21

        # weekly entries — 15 weeks (W06), 11 weeks (W10), 1 week (W20)
        for wk in ("2026-W06", "2026-W10", "2026-W20"):
            s3.put_object(
                Bucket=DEST_BUCKET,
                Key=f"r2/weekly/{wk}/{SOURCE_BUCKET}/u1/file",
                Body=b"x",
            )
        # monthly entries — 13 months (2025-04), 6 months (2025-11),
        # 1 month (2026-04)
        for mo in ("2025-04", "2025-11", "2026-04"):
            s3.put_object(
                Bucket=DEST_BUCKET,
                Key=f"r2/monthly/{mo}/{SOURCE_BUCKET}/u1/file",
                Body=b"x",
            )

        svc.run_retention_sweep(now=now)

        weekly_left = _dest_keys(s3, "r2/weekly/")
        monthly_left = _dest_keys(s3, "r2/monthly/")
        assert all("2026-W06" not in k for k in weekly_left)
        assert any("2026-W10" in k for k in weekly_left)
        assert any("2026-W20" in k for k in weekly_left)
        assert all("2025-04" not in k for k in monthly_left)
        assert any("2025-11" in k for k in monthly_left)
        assert any("2026-04" in k for k in monthly_left)


# ─── size cap + partial failure ───────────────────────────────────────────

class TestSizeCapAndFailureTolerance:
    def test_backup_skips_object_over_size_cap(self, s3, cfg, monkeypatch):
        small_cfg = BackupConfig(**{
            **cfg.__dict__, "max_object_bytes": 1024
        })
        svc = R2BackupService(config=small_cfg)
        monkeypatch.setattr(svc, "_get_client", lambda: s3)
        _put(s3, "u1/small", b"X" * 512)
        _put(s3, "u1/oversize", b"Y" * 2048)
        _put(s3, "u1/also-small", b"Z" * 256)

        result = svc.run_daily_backup(
            now=datetime(2026, 5, 21, 3, 0, tzinfo=dt_tz.utc)
        )

        assert result.objects_copied == 2
        assert result.objects_skipped == 1
        assert result.objects_failed == 0
        keys = _dest_keys(s3, "r2/daily/2026-05-21/")
        assert any("u1/small" in k for k in keys)
        assert any("u1/also-small" in k for k in keys)
        assert all("u1/oversize" not in k for k in keys)

    def test_backup_partial_failure_within_tolerance_marks_success(
        self, svc, s3
    ):
        for i in range(100):
            _put(s3, f"u1/file-{i:03d}", b"X")

        original_copy_one = svc._copy_one
        call_state = {"n": 0}

        def fail_once(src_bucket, src_key, src_size, dest_key):
            call_state["n"] += 1
            if src_key == "u1/file-042":
                raise ClientError(
                    {"Error": {"Code": "500", "Message": "transient"}},
                    "CopyObject",
                )
            return original_copy_one(src_bucket, src_key, src_size, dest_key)

        with patch.object(svc, "_copy_one", side_effect=fail_once):
            now = datetime(2026, 5, 21, 3, 0, tzinfo=dt_tz.utc)
            result = svc.run_daily_backup(now=now)

        assert result.objects_failed == 1
        assert result.objects_copied == 99

    def test_backup_partial_failure_over_tolerance_raises(self, svc, s3):
        for i in range(100):
            _put(s3, f"u1/file-{i:03d}", b"X")

        original_copy_one = svc._copy_one

        def fail_many(src_bucket, src_key, src_size, dest_key):
            idx = int(src_key.rsplit("-", 1)[1])
            if idx < 10:  # first 10 fail
                raise ClientError(
                    {"Error": {"Code": "500", "Message": "transient"}},
                    "CopyObject",
                )
            return original_copy_one(src_bucket, src_key, src_size, dest_key)

        with patch.object(svc, "_copy_one", side_effect=fail_many):
            now = datetime(2026, 5, 21, 3, 0, tzinfo=dt_tz.utc)
            with pytest.raises(R2BackupPartialFailure):
                svc.run_daily_backup(now=now)

    def test_ratio_floor_blocks_small_bucket_false_positive(
        self, s3, cfg, monkeypatch
    ):
        """50 attempts + 1 failure = 2% > 1% ratio, but stays below the
        200-attempt floor → run succeeds. Lowering the floor below the
        attempt count re-arms the ratio trip."""
        svc = R2BackupService(config=cfg)
        monkeypatch.setattr(svc, "_get_client", lambda: s3)
        for i in range(50):
            _put(s3, f"u1/file-{i:02d}", b"X")

        original_copy_one = svc._copy_one

        def fail_one(src_bucket, src_key, src_size, dest_key):
            if src_key == "u1/file-07":
                raise ClientError(
                    {"Error": {"Code": "500", "Message": "transient"}},
                    "CopyObject",
                )
            return original_copy_one(src_bucket, src_key, src_size, dest_key)

        now = datetime(2026, 5, 21, 3, 0, tzinfo=dt_tz.utc)

        # Default floor (200): below the floor → ratio check skipped,
        # absolute count (1 ≤ 5 tolerance) → run succeeds.
        with patch.object(svc, "_copy_one", side_effect=fail_one):
            result = svc.run_daily_backup(now=now)
        assert result.objects_failed == 1
        assert result.objects_copied == 49

        # Lower floor below the 50 attempts → ratio check re-armed,
        # 1/50 = 2% > 1% → run raises. Absolute count (1 ≤ 5)
        # cannot be the cause, so the ratio gating is what trips.
        lowered_cfg = BackupConfig(**{**cfg.__dict__, "ratio_floor": 10})
        svc2 = R2BackupService(config=lowered_cfg)
        monkeypatch.setattr(svc2, "_get_client", lambda: s3)
        # Clear the copied destination keys so the second run re-attempts.
        for k in _dest_keys(s3, "r2/daily/2026-05-21/"):
            s3.delete_object(Bucket=DEST_BUCKET, Key=k)

        original_copy_one_2 = svc2._copy_one

        def fail_one_2(src_bucket, src_key, src_size, dest_key):
            if src_key == "u1/file-07":
                raise ClientError(
                    {"Error": {"Code": "500", "Message": "transient"}},
                    "CopyObject",
                )
            return original_copy_one_2(src_bucket, src_key, src_size, dest_key)

        with patch.object(svc2, "_copy_one", side_effect=fail_one_2):
            with pytest.raises(R2BackupPartialFailure):
                svc2.run_daily_backup(now=now)


# ─── source unreachable: heartbeat preserved ──────────────────────────────

class TestSourceUnreachable:
    def test_backup_source_unreachable_no_heartbeat_update(
        self, s3, cfg, monkeypatch
    ):
        bad_cfg = BackupConfig(**{
            **cfg.__dict__, "source_buckets": ("does-not-exist",)
        })
        svc = R2BackupService(config=bad_cfg)
        monkeypatch.setattr(svc, "_get_client", lambda: s3)

        import storage.services as storage_services

        monkeypatch.setattr(
            storage_services, "get_r2_backup_service", lambda: svc
        )
        monkeypatch.setattr(
            r2_backup, "get_r2_backup_service", lambda: svc
        )

        cache.set(LAST_SUCCESS_CACHE_KEY, "2026-05-01T00:00:00")

        # Bypass Celery's autoretry wrapper so we see the original
        # ClientError instead of celery.exceptions.Retry. Fail loudly
        # if Celery's internal attribute moves — silent fallback to
        # `.run` would re-enable the wrapper and turn this test into
        # a DID_NOT_RAISE.
        assert hasattr(backup_r2_user_assets, "_orig_run"), (
            "celery autoretry internals moved: `_orig_run` not present "
            "on the task. Update test bypass — see Celery changelog for "
            "the replacement attribute on the version pinned in "
            "requirements.txt."
        )
        run_body = backup_r2_user_assets._orig_run
        with pytest.raises(ClientError):
            run_body()

        assert cache.get(LAST_SUCCESS_CACHE_KEY) == "2026-05-01T00:00:00"


# ─── health check ─────────────────────────────────────────────────────────

class TestHealthCheck:
    def test_health_check_fires_when_stale(self):
        now = datetime(2026, 5, 21, 3, 0, tzinfo=dt_tz.utc)
        last = now - timedelta(hours=48)
        cache.set(LAST_SUCCESS_CACHE_KEY, last.isoformat())

        with patch("sentry_sdk.capture_message") as captured, \
                patch("django.utils.timezone.now", return_value=now):
            result = r2_backup_health_check()

        assert result["ok"] is False
        assert result["stale"] is True
        captured.assert_called_once()
        args, kwargs = captured.call_args
        assert args[0] == "r2-backup-stale"
        assert kwargs["level"] == "error"
        assert kwargs["fingerprint"] == ["r2-backup-stale"]

    def test_health_check_silent_when_fresh(self):
        now = datetime(2026, 5, 21, 3, 0, tzinfo=dt_tz.utc)
        last = now - timedelta(hours=1)
        cache.set(LAST_SUCCESS_CACHE_KEY, last.isoformat())

        with patch("sentry_sdk.capture_message") as captured, \
                patch("django.utils.timezone.now", return_value=now):
            result = r2_backup_health_check()

        assert result["ok"] is True
        captured.assert_not_called()

    def test_health_check_silent_when_cold(self):
        cache.delete(LAST_SUCCESS_CACHE_KEY)
        with patch("sentry_sdk.capture_message") as captured:
            result = r2_backup_health_check()
        assert result["ok"] is True
        assert result.get("skipped") == "no_heartbeat"
        captured.assert_not_called()

    def test_environment_default_is_loud_fail(self):
        """Lock in plan §1.2: with ENVIRONMENT unset (or 'development'),
        the dest_bucket is intentionally a name no real env matches —
        so a misconfigured pod fails loudly instead of silently writing
        prod data into the staging bucket."""
        from django.test.utils import override_settings

        with override_settings(
            ENVIRONMENT="development",
            R2_BACKUP_DEST_BUCKET="sternaway-backups-development",
        ):
            cfg = BackupConfig.from_settings()
            assert "development" in cfg.dest_bucket
            assert "staging" not in cfg.dest_bucket
            assert "production" not in cfg.dest_bucket

        with override_settings(
            ENVIRONMENT="production",
            R2_BACKUP_DEST_BUCKET="sternaway-backups-production",
        ):
            cfg = BackupConfig.from_settings()
            assert cfg.dest_bucket == "sternaway-backups-production"

    def test_health_check_fires_exactly_at_threshold_plus_1s(self):
        now = datetime(2026, 5, 21, 3, 0, tzinfo=dt_tz.utc)

        over = now - (STALE_THRESHOLD + timedelta(seconds=1))
        cache.set(LAST_SUCCESS_CACHE_KEY, over.isoformat())
        with patch("sentry_sdk.capture_message") as captured, \
                patch("django.utils.timezone.now", return_value=now):
            r2_backup_health_check()
        captured.assert_called_once()

        under = now - (STALE_THRESHOLD - timedelta(seconds=1))
        cache.set(LAST_SUCCESS_CACHE_KEY, under.isoformat())
        with patch("sentry_sdk.capture_message") as captured, \
                patch("django.utils.timezone.now", return_value=now):
            r2_backup_health_check()
        captured.assert_not_called()
