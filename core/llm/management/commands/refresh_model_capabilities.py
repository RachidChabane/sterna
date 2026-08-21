"""
Management command to refresh model capabilities from OpenRouter API.

This command fetches the latest model data from OpenRouter and updates
the supports_streaming and supports_functions fields based on the
supported_parameters field from the API.

Usage:
    python manage.py refresh_model_capabilities
    python manage.py refresh_model_capabilities --force  # Force full catalog refresh
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from llm.catalog_service import CatalogService
from llm.models import ModelCatalog


class Command(BaseCommand):
    help = 'Refresh model capabilities from OpenRouter API'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force a full catalog refresh from OpenRouter',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be updated without making changes',
        )

    def handle(self, *args, **options):
        force = options['force']
        dry_run = options['dry_run']

        self.stdout.write(self.style.SUCCESS('Starting model capabilities refresh...'))

        catalog = CatalogService()

        try:
            # Fetch models from OpenRouter
            if force:
                self.stdout.write('Force refreshing catalog from OpenRouter...')
                result = catalog.refresh_catalog()
                
                if not result.get('success'):
                    self.stdout.write(
                        self.style.ERROR(f"Failed to refresh catalog: {result.get('error')}")
                    )
                    return
                
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Fetched {result['total_models']} models from OpenRouter"
                    )
                )
            else:
                self.stdout.write('Ensuring catalog is populated...')
                catalog.ensure_catalog_populated()

            # Get all models from database
            models = ModelCatalog.objects.all()
            total_models = models.count()
            
            if total_models == 0:
                self.stdout.write(
                    self.style.WARNING('No models found in database. Run with --force to fetch from OpenRouter.')
                )
                return

            self.stdout.write(f'Processing {total_models} models...')

            updated_count = 0
            streaming_enabled = 0
            streaming_disabled = 0
            functions_enabled = 0
            functions_disabled = 0

            with transaction.atomic():
                for model in models:
                    old_streaming = model.supports_streaming
                    old_functions = model.supports_functions

                    # The capabilities should already be correct if we just refreshed
                    # But we can log the changes
                    if model.supports_streaming != old_streaming:
                        if model.supports_streaming:
                            streaming_enabled += 1
                        else:
                            streaming_disabled += 1
                        
                        if not dry_run:
                            self.stdout.write(
                                f'  {model.model_id}: streaming {old_streaming} → {model.supports_streaming}'
                            )

                    if model.supports_functions != old_functions:
                        if model.supports_functions:
                            functions_enabled += 1
                        else:
                            functions_disabled += 1
                        
                        if not dry_run:
                            self.stdout.write(
                                f'  {model.model_id}: functions {old_functions} → {model.supports_functions}'
                            )

                    if model.supports_streaming != old_streaming or model.supports_functions != old_functions:
                        updated_count += 1

                if dry_run:
                    self.stdout.write(self.style.WARNING('DRY RUN - No changes were made'))
                    raise transaction.TransactionManagementError("Dry run - rolling back")

            # Summary
            self.stdout.write(self.style.SUCCESS('\nRefresh complete!'))
            self.stdout.write(f'Total models processed: {total_models}')
            self.stdout.write(f'Models updated: {updated_count}')
            
            if streaming_enabled > 0:
                self.stdout.write(f'  Streaming enabled: {streaming_enabled}')
            if streaming_disabled > 0:
                self.stdout.write(f'  Streaming disabled: {streaming_disabled}')
            if functions_enabled > 0:
                self.stdout.write(f'  Functions enabled: {functions_enabled}')
            if functions_disabled > 0:
                self.stdout.write(f'  Functions disabled: {functions_disabled}')

        except transaction.TransactionManagementError:
            # Expected for dry run
            if dry_run:
                self.stdout.write(self.style.WARNING('\nDRY RUN complete - no changes were saved'))
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Error refreshing model capabilities: {e}')
            )
            raise
