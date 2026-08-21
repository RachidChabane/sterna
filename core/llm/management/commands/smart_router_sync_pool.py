"""
Management command to sync the smart router's routing pool from settings.

Usage:
    python manage.py smart_router_sync_pool
    python manage.py smart_router_sync_pool --dry-run
"""

from django.core.cache import cache
from django.core.management.base import BaseCommand

from llm.models import ModelCatalog, RoutingPool

DEFAULT_POOL = [
    {"model_id": "google/gemini-2.0-flash-001", "cost_tier": "budget", "min": 0, "max": 30, "priority": 10},
    {"model_id": "google/gemini-2.5-flash-lite", "cost_tier": "budget", "min": 0, "max": 40, "priority": 5},
    {"model_id": "anthropic/claude-haiku-4.5", "cost_tier": "balanced", "min": 15, "max": 65, "priority": 10},
    {"model_id": "anthropic/claude-sonnet-4.5", "cost_tier": "premium", "min": 40, "max": 90, "priority": 10},
    {"model_id": "anthropic/claude-opus-4.6", "cost_tier": "premium", "min": 70, "max": 100, "priority": 5},
]


class Command(BaseCommand):
    help = "Sync the smart router's routing pool from settings configuration"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Preview changes without applying them",
        )

    def handle(self, *args, **options):
        from django.conf import settings

        dry_run = options["dry_run"]
        pool_config = getattr(settings, "SMART_ROUTER_ROUTING_POOL", None) or DEFAULT_POOL

        self.stdout.write(f"Syncing {len(pool_config)} pool entries...")

        created = 0
        updated = 0
        skipped = 0

        for entry in pool_config:
            model_id = entry["model_id"]
            catalog_model = ModelCatalog.objects.filter(model_id=model_id).first()

            if not catalog_model:
                self.stdout.write(self.style.WARNING(f"  SKIP {model_id} (not in catalog)"))
                skipped += 1
                continue

            defaults = {
                "is_active": True,
                "cost_tier": entry["cost_tier"],
                "min_complexity_score": entry["min"],
                "max_complexity_score": entry["max"],
                "priority": entry["priority"],
            }

            if dry_run:
                existing = RoutingPool.objects.filter(model=catalog_model).first()
                if existing:
                    self.stdout.write(f"  UPDATE {model_id}: {defaults}")
                    updated += 1
                else:
                    self.stdout.write(f"  CREATE {model_id}: {defaults}")
                    created += 1
            else:
                _, was_created = RoutingPool.objects.update_or_create(
                    model=catalog_model,
                    defaults=defaults,
                )
                if was_created:
                    self.stdout.write(self.style.SUCCESS(f"  CREATED {model_id}"))
                    created += 1
                else:
                    self.stdout.write(f"  UPDATED {model_id}")
                    updated += 1

        # Invalidate pool cache
        if not dry_run:
            cache.delete("smart_router:routing_pool")

        prefix = "[DRY RUN] " if dry_run else ""
        self.stdout.write(
            self.style.SUCCESS(
                f"\n{prefix}Done: {created} created, {updated} updated, {skipped} skipped"
            )
        )
