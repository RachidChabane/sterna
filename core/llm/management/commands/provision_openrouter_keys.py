"""
Management command to provision OpenRouter API keys for existing users.

Run after migration to ensure all users have their own API keys.

Usage:
    python manage.py provision_openrouter_keys
    python manage.py provision_openrouter_keys --dry-run
    python manage.py provision_openrouter_keys --force  # Re-provision even if key exists
"""

import logging
from django.core.management.base import BaseCommand
from django.conf import settings

from authentication.models import User
from llm.services.openrouter_keys import OpenRouterKeyService

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Provision OpenRouter API keys for existing users who don't have one"

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be done without making changes',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Re-provision keys even for users who already have one',
        )
        parser.add_argument(
            '--user-id',
            type=str,
            help='Provision key for a specific user ID only',
        )
        parser.add_argument(
            '--limit',
            type=int,
            help='Limit the number of users to process',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        force = options['force']
        user_id = options.get('user_id')
        limit = options.get('limit')

        # Check if provisioning key is configured
        provisioning_key = getattr(settings, 'OPENROUTER_PROVISIONING_KEY', '')
        if not provisioning_key:
            self.stderr.write(self.style.ERROR(
                'OPENROUTER_PROVISIONING_KEY not configured in settings. '
                'Please set it in your .env file.'
            ))
            return

        # Initialize the service
        service = OpenRouterKeyService()

        # Build queryset
        users = User.objects.filter(is_active=True)

        if user_id:
            users = users.filter(id=user_id)

        if not force:
            # Only users without an API key
            users = users.filter(openrouter_api_key__isnull=True) | \
                    users.filter(openrouter_api_key='')

        if limit:
            users = users[:limit]

        users_list = list(users)
        total = len(users_list)

        if total == 0:
            self.stdout.write(self.style.SUCCESS(
                'No users need API key provisioning.'
            ))
            return

        self.stdout.write(f'Found {total} users to process...')

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN - no changes will be made'))

        success_count = 0
        error_count = 0

        for i, user in enumerate(users_list, 1):
            email = user.email
            self.stdout.write(f'[{i}/{total}] Processing {email}... ', ending='')

            if dry_run:
                self.stdout.write(self.style.SUCCESS('would provision'))
                success_count += 1
                continue

            try:
                key = service.provision_key_for_user(user)
                if key:
                    self.stdout.write(self.style.SUCCESS('provisioned'))
                    success_count += 1
                else:
                    self.stdout.write(self.style.WARNING('skipped (no key returned)'))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'error: {e}'))
                error_count += 1
                logger.exception(f'Failed to provision key for {email}')

        # Summary
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(f'Successfully provisioned: {success_count}'))
        if error_count:
            self.stdout.write(self.style.ERROR(f'Errors: {error_count}'))

        if dry_run:
            self.stdout.write(self.style.WARNING(
                '\nThis was a dry run. Run without --dry-run to make changes.'
            ))
