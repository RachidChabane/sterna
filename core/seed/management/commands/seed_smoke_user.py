"""Seed the smoke-test user (task 28).

Idempotent. Reads SMOKE_TEST_USER_PASSWORD from the environment so the
secret never lives in the repo. The smoke pytest suite logs in as this
user via /api/auth/login/ — the same code path real users take, no
backdoor.
"""
import os

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from authentication.models import User

SMOKE_EMAIL_DEFAULT = "smoke@sterna-internal.test"
MIN_PASSWORD_LEN = 16


class Command(BaseCommand):
    help = (
        "Seed the smoke-test user. Idempotent. Reads "
        "SMOKE_TEST_USER_PASSWORD (>=16 chars) from env."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--email",
            default=SMOKE_EMAIL_DEFAULT,
            help=f"Smoke-test user email (default: {SMOKE_EMAIL_DEFAULT})",
        )

    def handle(self, *args, email, **opts):
        pw = os.environ.get("SMOKE_TEST_USER_PASSWORD")
        if not pw:
            raise CommandError(
                "SMOKE_TEST_USER_PASSWORD env var is not set; refusing to "
                "seed smoke user without a password."
            )
        if len(pw) < MIN_PASSWORD_LEN:
            raise CommandError(
                f"SMOKE_TEST_USER_PASSWORD must be >= {MIN_PASSWORD_LEN} "
                f"chars (got {len(pw)})."
            )

        with transaction.atomic():
            user, created = User.objects.update_or_create(
                email=email,
                defaults={
                    "is_active": True,
                    "is_verified": True,
                    "is_staff": False,
                    "is_superuser": False,
                },
            )
            user.set_password(pw)
            user.save(update_fields=["password"])

        action = "created" if created else "updated"
        self.stdout.write(
            self.style.SUCCESS(f"Smoke user {action}: {email}")
        )
