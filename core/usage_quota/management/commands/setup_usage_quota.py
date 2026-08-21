"""Management command to set up initial usage quota data."""

from django.core.management.base import BaseCommand
from django.core.management import call_command
from django.db import transaction

from usage_quota.models import SubscriptionPlan, ServicePricing


class Command(BaseCommand):
    help = 'Set up initial subscription plans and service pricing for the usage quota system'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force reload even if data already exists',
        )

    def handle(self, *args, **options):
        force = options.get('force', False)

        # Check if data already exists
        plans_exist = SubscriptionPlan.objects.exists()
        pricing_exists = ServicePricing.objects.exists()

        if plans_exist or pricing_exists:
            if not force:
                self.stdout.write(
                    self.style.WARNING(
                        'Usage quota data already exists. Use --force to reload.'
                    )
                )
                return
            else:
                self.stdout.write('Clearing existing data...')
                with transaction.atomic():
                    ServicePricing.objects.all().delete()
                    # Don't delete plans if they have subscriptions
                    SubscriptionPlan.objects.filter(subscriptions__isnull=True).delete()

        # Load subscription plans
        self.stdout.write('Loading subscription plans...')
        try:
            call_command('loaddata', 'usage_quota/fixtures/initial_plans.json', verbosity=0)
            plan_count = SubscriptionPlan.objects.count()
            self.stdout.write(
                self.style.SUCCESS(f'  Loaded {plan_count} subscription plans')
            )
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'  Failed to load plans: {e}')
            )

        # Load service pricing
        self.stdout.write('Loading service pricing...')
        try:
            call_command('loaddata', 'usage_quota/fixtures/service_pricing.json', verbosity=0)
            pricing_count = ServicePricing.objects.count()
            self.stdout.write(
                self.style.SUCCESS(f'  Loaded {pricing_count} service pricing entries')
            )
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'  Failed to load pricing: {e}')
            )

        # Summary
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('Usage quota setup complete!'))
        self.stdout.write('')
        self.stdout.write('Available subscription plans:')
        for plan in SubscriptionPlan.objects.all():
            default_marker = ' (default)' if plan.is_default else ''
            self.stdout.write(
                f'  - {plan.display_name}: ${plan.weekly_limit_usd}/week, '
                f'${plan.session_limit_usd}/session{default_marker}'
            )
