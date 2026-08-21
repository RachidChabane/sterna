"""Fail loudly if the Stripe key shape disagrees with the current env.

Wired into the staging deploy workflow as a post-deploy step (see
.github/workflows/deploy-staging.yml). The same check should run in
prod's deploy workflow (task 11 only touches staging; prod wires in
a follow-up).

Exit codes:
  0 = ok (key prefix matches expected env)
  1 = mismatch — e.g. dev/staging pointed at sk_live_…, OR prod
       pointed at sk_test_…, OR key unset where it must be set.
"""

import sys

from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = (
        "Verify STRIPE_API_KEY prefix is correct for DJANGO_ENV. "
        "Exits 1 on mismatch."
    )

    def handle(self, *args, **opts):
        env = getattr(settings, "DJANGO_ENV", "dev")
        key = settings.STRIPE_API_KEY or ""
        live = settings.STRIPE_LIVE_MODE

        if env in ("dev", "test"):
            if live:
                self.stderr.write(self.style.ERROR(
                    f"FATAL: DJANGO_ENV={env} but STRIPE_API_KEY starts "
                    f"with sk_live_. Refusing to run."
                ))
                sys.exit(1)
            self.stdout.write(self.style.SUCCESS(
                f"OK: DJANGO_ENV={env}, "
                f"key={'(unset)' if not key else 'sk_test_...'}, "
                f"live_mode=False"
            ))
            return

        if env == "staging":
            if not key:
                self.stderr.write(self.style.ERROR(
                    "FATAL: DJANGO_ENV=staging but STRIPE_API_KEY is unset."
                ))
                sys.exit(1)
            if live:
                self.stderr.write(self.style.ERROR(
                    "FATAL: DJANGO_ENV=staging but STRIPE_API_KEY starts "
                    "with sk_live_. Refusing to run."
                ))
                sys.exit(1)
            self.stdout.write(self.style.SUCCESS(
                "OK: staging on sk_test_…, live_mode=False"
            ))
            return

        if env == "prod":
            if not key:
                self.stderr.write(self.style.ERROR(
                    "FATAL: DJANGO_ENV=prod but STRIPE_API_KEY is unset."
                ))
                sys.exit(1)
            if not live:
                self.stderr.write(self.style.ERROR(
                    "FATAL: DJANGO_ENV=prod but STRIPE_API_KEY does NOT "
                    "start with sk_live_. Refusing to run."
                ))
                sys.exit(1)
            self.stdout.write(self.style.SUCCESS(
                "OK: prod on sk_live_…, live_mode=True"
            ))
            return

        self.stdout.write(self.style.WARNING(
            f"unknown DJANGO_ENV={env}; key check skipped"
        ))
