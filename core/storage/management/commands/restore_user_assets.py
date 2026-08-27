"""Restore a single user's R2 assets from a dated backup prefix."""

import sys

from botocore.exceptions import ClientError  # type: ignore[import-untyped]
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from authentication.models import User
from storage.services import get_r2_backup_service
from workspaces.services.workspace_storage import R2PathBuilder

VALID_KINDS = ("daily", "weekly", "monthly")


class Command(BaseCommand):
    help = "Restore a user's R2 assets from a dated backup prefix."

    def add_arguments(self, parser):
        parser.add_argument(
            "user", help="User id or email to restore."
        )
        parser.add_argument(
            "--from",
            dest="kind",
            required=True,
            choices=VALID_KINDS,
            help="Backup tier to read from.",
        )
        parser.add_argument(
            "--date",
            required=True,
            help=(
                "Backup date segment: YYYY-MM-DD for daily, "
                "YYYY-Www for weekly, YYYY-MM for monthly."
            ),
        )
        parser.add_argument(
            "--source-bucket",
            default=None,
            help=(
                "Source bucket to restore to. "
                "Default: settings.R2_BUCKET_NAME."
            ),
        )
        parser.add_argument(
            "--prefix",
            default=None,
            help="Optional sub-path narrowing within the user's tree.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="List what would be restored without writing.",
        )
        parser.add_argument(
            "--yes",
            action="store_true",
            help="Skip the confirmation prompt in live mode.",
        )

    def handle(self, *args, **options):
        user = self._resolve_user(options["user"])
        kind = options["kind"]
        date_segment = options["date"]
        source_bucket = (
            options["source_bucket"] or settings.R2_BUCKET_NAME
        )
        sub_prefix = options.get("prefix")
        dry_run: bool = options["dry_run"]
        yes: bool = options["yes"]

        svc = get_r2_backup_service()
        client = svc.client
        dest_bucket = svc.config.dest_bucket

        user_prefix = R2PathBuilder.user_prefix(str(user.id))
        if sub_prefix:
            user_prefix = f"{user_prefix}{sub_prefix.lstrip('/')}"
            if not user_prefix.endswith("/"):
                user_prefix += "/"

        backup_lookup_prefix = (
            f"r2/{kind}/{date_segment}/{source_bucket}/{user_prefix}"
        )

        matches: list[tuple[str, int]] = []
        paginator = client.get_paginator("list_objects_v2")
        try:
            for page in paginator.paginate(
                Bucket=dest_bucket, Prefix=backup_lookup_prefix
            ):
                for obj in page.get("Contents") or []:
                    matches.append((obj["Key"], obj["Size"]))
        except ClientError as exc:
            raise CommandError(
                f"Failed to list backup at {backup_lookup_prefix!r}: {exc}"
            ) from exc

        if not matches:
            self.stdout.write(
                self.style.WARNING(
                    f"No backup objects found under {backup_lookup_prefix!r}"
                )
            )
            sys.exit(2)

        prefix_strip = f"r2/{kind}/{date_segment}/{source_bucket}/"
        for dest_key, size in matches:
            original_key = dest_key[len(prefix_strip):]
            self.stdout.write(
                f"{size:>12d} bytes  {dest_key}  ->  "
                f"{source_bucket}/{original_key}"
            )

        self.stdout.write(
            self.style.NOTICE(
                f"\n{len(matches)} object(s) match. "
                f"Total bytes: {sum(s for _, s in matches)}"
            )
        )

        if dry_run:
            self.stdout.write(self.style.SUCCESS("Dry-run complete."))
            return

        if not yes:
            confirm = input(
                f"Restore {len(matches)} object(s) to "
                f"{source_bucket!r}? Type 'yes' to confirm: "
            )
            if confirm.strip().lower() != "yes":
                self.stdout.write(self.style.WARNING("Aborted."))
                sys.exit(2)

        failed: list[tuple[str, str]] = []
        copied = 0
        bytes_total = 0
        for dest_key, size in matches:
            original_key = dest_key[len(prefix_strip):]
            try:
                client.copy_object(
                    Bucket=source_bucket,
                    Key=original_key,
                    CopySource={"Bucket": dest_bucket, "Key": dest_key},
                )
            except ClientError as exc:
                failed.append((dest_key, str(exc)))
                continue
            copied += 1
            bytes_total += size

        self.stdout.write(
            self.style.SUCCESS(
                f"\nRestored {copied} object(s), {bytes_total} bytes."
            )
        )
        if failed:
            self.stdout.write(
                self.style.ERROR(f"\n{len(failed)} failure(s):")
            )
            for key, err in failed:
                self.stdout.write(f"  {key}: {err}")
            sys.exit(1)

    def _resolve_user(self, user_id_or_email: str) -> User:
        try:
            if "@" in user_id_or_email:
                return User.objects.get(email=user_id_or_email)
            return User.objects.get(id=user_id_or_email)
        except (User.DoesNotExist, ValueError) as exc:
            raise CommandError(
                f"User not found: {user_id_or_email!r}"
            ) from exc
