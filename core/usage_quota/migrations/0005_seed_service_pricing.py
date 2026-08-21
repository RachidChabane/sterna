"""Idempotent upsert of ServicePricing rows for the new service types and
the previously un-seeded ones (image_generation, kb_embedding, kb_query,
code_session).

ServicePricing has no unique constraint on (service, model_id) (only an
Index), so `update_or_create` would raise MultipleObjectsReturned when a
prior environment created multiple rows for the same key. We use the
safer pattern: pick the most-recent row by effective_from, update it if
present, else create a new one. Safe on fresh deploys, safe on prod,
safe to re-run.
"""

from decimal import Decimal

from django.db import migrations
from django.utils import timezone


PRICING_ROWS = [
    # MCP tool invocation — flat per-call placeholder
    {'service': 'mcp_tool_invocation', 'model_id': '',
     'price_per_request': Decimal('0.001000')},

    # Google Maps — per-endpoint pricing (model_id = endpoint name)
    {'service': 'google_maps', 'model_id': 'geocoding',
     'price_per_request': Decimal('0.005000')},
    {'service': 'google_maps', 'model_id': 'directions',
     'price_per_request': Decimal('0.005000')},
    {'service': 'google_maps', 'model_id': 'places_nearby',
     'price_per_request': Decimal('0.032000')},
    {'service': 'google_maps', 'model_id': 'places_details',
     'price_per_request': Decimal('0.017000')},
    {'service': 'google_maps', 'model_id': 'air_quality',
     'price_per_request': Decimal('0.005000')},
    {'service': 'google_maps', 'model_id': 'street_view',
     'price_per_request': Decimal('0.007000')},

    # Image generation — service-wide default fallback
    {'service': 'image_generation', 'model_id': '',
     'price_per_request': Decimal('0.020000')},

    # Knowledge Base embedding/query (text-embedding-3-large default)
    {'service': 'kb_embedding', 'model_id': '',
     'price_per_1m_input_tokens': Decimal('0.130000')},
    {'service': 'kb_query', 'model_id': '',
     'price_per_1m_input_tokens': Decimal('0.130000')},

    # Code session — fallback row; real cost comes from Claude CLI
    {'service': 'code_session', 'model_id': '',
     'price_per_request': Decimal('0.000000')},
]


def seed(apps, schema_editor):
    """Idempotent upsert of PRICING_ROWS. See module docstring."""
    ServicePricing = apps.get_model('usage_quota', 'ServicePricing')
    effective_from = timezone.now()
    for row in PRICING_ROWS:
        defaults = {k: v for k, v in row.items()
                    if k not in ('service', 'model_id')}
        defaults.update({
            'is_active': True,
            'effective_from': effective_from,
        })
        existing = (
            ServicePricing.objects
            .filter(service=row['service'], model_id=row['model_id'])
            .order_by('-effective_from')
            .first()
        )
        if existing is None:
            ServicePricing.objects.create(
                service=row['service'],
                model_id=row['model_id'],
                **defaults,
            )
        else:
            for k, v in defaults.items():
                setattr(existing, k, v)
            existing.save()


def unseed(apps, schema_editor):
    """Reverse migration: delete rows matching the seed keys."""
    ServicePricing = apps.get_model('usage_quota', 'ServicePricing')
    for row in PRICING_ROWS:
        ServicePricing.objects.filter(
            service=row['service'],
            model_id=row['model_id'],
        ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('usage_quota', '0004_add_service_types'),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
