"""Orchestrate all seed-data commands (task 28).

Each child command is independently idempotent. seed_all wraps them so
operators can re-run a single command after Terraform/Helm/Kustomize
applies a fresh cluster. Failures in REQUIRED steps are aggregated and
the overall command exits non-zero AFTER attempting every remaining
step (full-visibility logging in one CI run).

`seed_email_templates` is intentionally omitted: there is no
EmailTemplate model in the codebase as of task 28. Re-evaluate when
one ships.
"""
import logging

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError

logger = logging.getLogger(__name__)

# (name, child_args, required, supports_dry_run)
REQUIRED_STEPS = [
    ("sync_stripe_prices", [], True, True),
    ("setup_usage_quota", [], True, False),
    ("seed_preconfigured_servers", [], True, True),
    ("seed_smoke_user", [], True, False),
]


class Command(BaseCommand):
    help = "Orchestrate all idempotent seed-data commands."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Pass --dry-run to children that support it.",
        )
        parser.add_argument(
            "--skip-smoke-user",
            action="store_true",
            help="Skip seed_smoke_user (zero-trust prod posture).",
        )

    def handle(self, *args, dry_run, skip_smoke_user, **opts):
        failures = []
        for (name, child_args, required, supports_dry_run) in REQUIRED_STEPS:
            if name == "seed_smoke_user" and skip_smoke_user:
                self.stdout.write(
                    self.style.WARNING(f"  [skip] {name} (--skip-smoke-user)")
                )
                continue
            self.stdout.write(f"  [run]  {name}")
            invoke_args = list(child_args)
            if dry_run and supports_dry_run:
                invoke_args.append("--dry-run")
            try:
                call_command(name, *invoke_args)
                self.stdout.write(self.style.SUCCESS(f"  [ok]   {name}"))
            except (CommandError, Exception) as exc:  # noqa: BLE001
                # Broad catch: each child may raise anything (Stripe API,
                # integrity errors, …). We want all failures surfaced in
                # one CI run, not just the first.
                self.stdout.write(self.style.ERROR(f"  [fail] {name}: {exc}"))
                logger.exception("seed_all step failed: %s", name)
                if required:
                    failures.append(name)
        if failures:
            raise CommandError(
                "seed_all completed with failures in required steps: "
                f"{failures}"
            )
        self.stdout.write(self.style.SUCCESS("seed_all: all steps OK"))
