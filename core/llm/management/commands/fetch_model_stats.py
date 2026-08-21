"""
Management command to fetch model performance stats from OpenRouter.

This command fetches latency and throughput statistics for all models
in our database from OpenRouter's frontend API.

Usage:
    python manage.py fetch_model_stats
    python manage.py fetch_model_stats --limit 10  # Only process 10 models
    python manage.py fetch_model_stats --delay 0.5  # 500ms delay between requests
"""

import time
from django.core.management.base import BaseCommand
from django.utils import timezone

import httpx

from llm.models import ModelCatalog


# OpenRouter frontend stats endpoint
STATS_ENDPOINT = "https://openrouter.ai/api/frontend/stats/endpoint"


class Command(BaseCommand):
    help = 'Fetch model performance stats (latency, throughput) from OpenRouter'

    def add_arguments(self, parser):
        parser.add_argument(
            '--limit',
            type=int,
            default=0,
            help='Limit the number of models to process (0 = all)',
        )
        parser.add_argument(
            '--delay',
            type=float,
            default=0.2,
            help='Delay between API requests in seconds (default: 0.2)',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be fetched without making changes',
        )
        parser.add_argument(
            '--only-missing',
            action='store_true',
            help='Only fetch stats for models that don\'t have stats yet',
        )

    def handle(self, *args, **options):
        limit = options['limit']
        delay = options['delay']
        dry_run = options['dry_run']
        only_missing = options['only_missing']

        self.stdout.write(self.style.SUCCESS('Starting model stats fetch...'))

        # Get models from database
        queryset = ModelCatalog.objects.filter(is_available=True)

        if only_missing:
            queryset = queryset.filter(stats_updated_at__isnull=True)
            self.stdout.write('Filtering to models without stats...')

        models = list(queryset.order_by('model_id'))

        if limit > 0:
            models = models[:limit]

        total_models = len(models)

        if total_models == 0:
            self.stdout.write(self.style.WARNING('No models found to process.'))
            return

        self.stdout.write(f'Processing {total_models} models...')

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN - no changes will be made'))
            for model in models:
                self.stdout.write(f'  Would fetch stats for: {model.model_id}')
            return

        updated_count = 0
        error_count = 0
        no_stats_count = 0

        with httpx.Client(timeout=30.0) as client:
            for i, model in enumerate(models, 1):
                model_id = model.model_id

                self.stdout.write(f'[{i}/{total_models}] Fetching stats for {model_id}...', ending='')

                try:
                    response = client.get(
                        STATS_ENDPOINT,
                        params={
                            'permaslug': model_id,
                            'variant': 'standard',
                        },
                    )

                    if response.status_code != 200:
                        self.stdout.write(self.style.WARNING(f' HTTP {response.status_code}'))
                        error_count += 1
                        continue

                    data = response.json()
                    endpoints = data.get('data', [])

                    if not endpoints:
                        self.stdout.write(self.style.WARNING(' No data'))
                        no_stats_count += 1
                        continue

                    # Get stats from first endpoint (usually the main provider)
                    endpoint = endpoints[0]
                    stats = endpoint.get('stats')

                    if not stats:
                        self.stdout.write(self.style.WARNING(' No stats'))
                        no_stats_count += 1
                        continue

                    # Update model with stats
                    model.latency_p50 = int(stats.get('p50_latency')) if stats.get('p50_latency') else None
                    model.latency_p90 = int(stats.get('p90_latency')) if stats.get('p90_latency') else None
                    model.throughput_p50 = stats.get('p50_throughput')
                    model.throughput_p90 = stats.get('p90_throughput')
                    model.stats_updated_at = timezone.now()
                    model.save(update_fields=[
                        'latency_p50', 'latency_p90',
                        'throughput_p50', 'throughput_p90',
                        'stats_updated_at',
                    ])

                    self.stdout.write(self.style.SUCCESS(
                        f' OK (latency: {model.latency_p50}ms, throughput: {model.throughput_p50:.1f} tok/s)'
                    ))
                    updated_count += 1

                except httpx.TimeoutException:
                    self.stdout.write(self.style.ERROR(' Timeout'))
                    error_count += 1
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f' Error: {e}'))
                    error_count += 1

                # Rate limiting delay
                if i < total_models and delay > 0:
                    time.sleep(delay)

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('Stats fetch complete!'))
        self.stdout.write(f'  Updated: {updated_count}')
        self.stdout.write(f'  No stats available: {no_stats_count}')
        self.stdout.write(f'  Errors: {error_count}')
