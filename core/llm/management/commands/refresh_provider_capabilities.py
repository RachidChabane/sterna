"""
Management command to refresh provider capabilities from OpenRouter.

This command:
1. Fetches provider stream cancellation support from OpenRouter docs
2. Cross-references with API provider slugs
3. Updates Redis cache
4. Optionally updates the fallback JSON file

Usage:
    python manage.py refresh_provider_capabilities
    python manage.py refresh_provider_capabilities --force      # Force cache refresh
    python manage.py refresh_provider_capabilities --status     # Show cache status
"""

from django.core.management.base import BaseCommand
from django.core.cache import cache

from llm.provider_capabilities_service import (
    get_stream_cancellation_providers,
    get_cache_status,
    fetch_stream_cancellation_providers,
    CACHE_KEY_STREAM_CANCELLATION,
)


class Command(BaseCommand):
    help = 'Refresh provider capabilities from OpenRouter documentation'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force refresh by bypassing cache',
        )
        parser.add_argument(
            '--status',
            action='store_true',
            help='Show current cache status without refreshing',
        )
        parser.add_argument(
            '--clear-cache',
            action='store_true',
            help='Clear the cache and exit (useful for testing)',
        )

    def handle(self, *args, **options):
        force = options['force']
        show_status = options['status']
        clear_cache = options['clear_cache']

        # Handle clear cache
        if clear_cache:
            self.stdout.write('Clearing provider capabilities cache...')
            cache.delete(CACHE_KEY_STREAM_CANCELLATION)
            self.stdout.write(self.style.SUCCESS('Cache cleared successfully'))
            return

        # Handle status display
        if show_status:
            self.stdout.write(self.style.SUCCESS('Provider Capabilities Cache Status'))
            self.stdout.write('=' * 60)

            status = get_cache_status()

            if not status.get('cached'):
                self.stdout.write(self.style.WARNING('No data in cache'))
                self.stdout.write('\nRun with --force to fetch and cache data.')
                return

            self.stdout.write(f"Provider count: {status['provider_count']}")
            self.stdout.write(f"Source: {status['source']}")
            self.stdout.write(f"Fetched at: {status['fetched_at']}")
            self.stdout.write(f"Expires at: {status['expires_at']}")

            # Show sample providers
            providers = get_stream_cancellation_providers()
            sample = sorted(list(providers))[:10]
            self.stdout.write("\nSample providers (first 10):")
            for provider in sample:
                self.stdout.write(f"  - {provider}")

            if len(providers) > 10:
                self.stdout.write(f"  ... and {len(providers) - 10} more")

            return

        # Handle refresh
        self.stdout.write(self.style.SUCCESS('Refreshing provider capabilities...'))

        try:
            if force:
                self.stdout.write('Force refresh: Fetching fresh data from OpenRouter...')
                data = fetch_stream_cancellation_providers(force_refresh=True)

                # Update cache
                from llm.provider_capabilities_service import CACHE_TTL
                cache.set(CACHE_KEY_STREAM_CANCELLATION, data, CACHE_TTL)

                providers = set(data.get('supported_slugs', []))
            else:
                self.stdout.write('Using cached data if available...')
                providers = get_stream_cancellation_providers()

            # Display results
            self.stdout.write('\n' + '=' * 60)
            self.stdout.write(self.style.SUCCESS('Refresh complete!'))
            self.stdout.write('=' * 60)

            self.stdout.write(f"\nTotal providers supporting stream cancellation: {len(providers)}")

            # Show providers
            self.stdout.write("\nProviders:")
            for provider in sorted(providers):
                self.stdout.write(f"  - {provider}")

            # Show cache status
            self.stdout.write('\n' + '=' * 60)
            self.stdout.write('Cache Status:')
            self.stdout.write('=' * 60)
            status = get_cache_status()
            self.stdout.write(f"Cached: {status.get('cached', False)}")
            self.stdout.write(f"Source: {status.get('source', 'N/A')}")
            self.stdout.write(f"Fetched at: {status.get('fetched_at', 'N/A')}")
            self.stdout.write(f"Expires at: {status.get('expires_at', 'N/A')}")

            self.stdout.write('\n' + self.style.SUCCESS('Done!'))

        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Error refreshing provider capabilities: {e}')
            )
            import traceback
            self.stdout.write(traceback.format_exc())
            raise
