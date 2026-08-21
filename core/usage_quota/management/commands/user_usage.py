"""
Management command to get detailed usage info for a specific user.

Usage:
    python manage.py user_usage <email_or_id>
    python manage.py user_usage user@example.com
    python manage.py user_usage --all-time user@example.com
"""

from decimal import Decimal
from datetime import timedelta
from django.core.management.base import BaseCommand, CommandError
from django.db import models
from django.utils import timezone

from authentication.models import User
from usage_quota.models import UsageLog, UserSubscription, ServiceType, FeatureType
from usage_quota.services.quota_service import (
    get_quota_service,
    WEEKLY_WINDOW_DAYS,
    SESSION_WINDOW_HOURS,
)


class Command(BaseCommand):
    help = 'Get detailed usage info for a specific user'

    def add_arguments(self, parser):
        parser.add_argument(
            'user',
            type=str,
            help='User email or UUID'
        )
        parser.add_argument(
            '--all-time',
            action='store_true',
            help='Show all-time usage instead of current window'
        )
        parser.add_argument(
            '--days',
            type=int,
            default=None,
            help='Show usage for the last N days'
        )

    def handle(self, *args, **options):
        user_identifier = options['user']
        all_time = options['all_time']
        days = options['days']

        # Find user
        try:
            if '@' in user_identifier:
                user = User.objects.get(email=user_identifier)
            else:
                user = User.objects.get(id=user_identifier)
        except User.DoesNotExist:
            raise CommandError(f'User not found: {user_identifier}')

        self.stdout.write(self.style.SUCCESS(f'\n{"="*60}'))
        self.stdout.write(self.style.SUCCESS(f'Usage Report for: {user.email}'))
        self.stdout.write(self.style.SUCCESS(f'User ID: {user.id}'))
        self.stdout.write(self.style.SUCCESS(f'{"="*60}\n'))

        # Get subscription info
        try:
            subscription = UserSubscription.objects.select_related('plan').get(
                user=user, is_active=True
            )
            self.stdout.write(f'Plan: {subscription.plan.display_name}')
            self.stdout.write(f'Weekly Limit: ${subscription.effective_weekly_limit}')
            self.stdout.write(f'Session Limit: ${subscription.effective_session_limit}')

            # Window status
            self.stdout.write('\n--- Window Status ---')
            if subscription.weekly_window_start:
                weekly_end = subscription.weekly_window_start + timedelta(days=WEEKLY_WINDOW_DAYS)
                is_active = timezone.now() < weekly_end
                status = self.style.SUCCESS('ACTIVE') if is_active else self.style.WARNING('EXPIRED')
                self.stdout.write(f'Weekly Window: {status}')
                self.stdout.write(f'  Started: {subscription.weekly_window_start}')
                self.stdout.write(f'  Ends: {weekly_end}')
            else:
                self.stdout.write(f'Weekly Window: {self.style.WARNING("NOT STARTED")}')

            if subscription.session_window_start:
                session_end = subscription.session_window_start + timedelta(hours=SESSION_WINDOW_HOURS)
                is_active = timezone.now() < session_end
                status = self.style.SUCCESS('ACTIVE') if is_active else self.style.WARNING('EXPIRED')
                self.stdout.write(f'Session Window: {status}')
                self.stdout.write(f'  Started: {subscription.session_window_start}')
                self.stdout.write(f'  Ends: {session_end}')
            else:
                self.stdout.write(f'Session Window: {self.style.WARNING("NOT STARTED")}')

        except UserSubscription.DoesNotExist:
            self.stdout.write(self.style.WARNING('No active subscription'))
            subscription = None

        # Determine time range
        if all_time:
            window_start = None
            period_label = 'All Time'
        elif days:
            window_start = timezone.now() - timedelta(days=days)
            period_label = f'Last {days} Days'
        elif subscription and subscription.weekly_window_start:
            weekly_end = subscription.weekly_window_start + timedelta(days=WEEKLY_WINDOW_DAYS)
            if timezone.now() < weekly_end:
                window_start = subscription.weekly_window_start
                period_label = 'Current Weekly Window'
            else:
                window_start = timezone.now() - timedelta(days=WEEKLY_WINDOW_DAYS)
                period_label = f'Last {WEEKLY_WINDOW_DAYS} Days (window expired)'
        else:
            window_start = timezone.now() - timedelta(days=WEEKLY_WINDOW_DAYS)
            period_label = f'Last {WEEKLY_WINDOW_DAYS} Days'

        self.stdout.write(f'\n--- Usage ({period_label}) ---\n')

        # Build query
        query = UsageLog.objects.filter(user=user)
        if window_start:
            query = query.filter(timestamp__gte=window_start)

        # Global stats
        global_stats = query.aggregate(
            total_cost=models.Sum('cost_usd'),
            total_requests=models.Count('id'),
            total_tokens=models.Sum('total_tokens'),
            total_chars=models.Sum('character_count'),
            total_audio=models.Sum('audio_seconds'),
        )

        total_cost = global_stats['total_cost'] or Decimal('0')
        self.stdout.write(self.style.HTTP_INFO(f'TOTAL USAGE: ${total_cost:.6f}'))
        self.stdout.write(f'Total Requests: {global_stats["total_requests"] or 0}')
        self.stdout.write('')

        # By Service
        self.stdout.write(self.style.HTTP_INFO('BY SERVICE:'))
        self.stdout.write('-' * 50)

        service_stats = query.values('service').annotate(
            cost=models.Sum('cost_usd'),
            requests=models.Count('id'),
            tokens=models.Sum('total_tokens'),
            chars=models.Sum('character_count'),
            audio=models.Sum('audio_seconds'),
            prompt_tokens=models.Sum('prompt_tokens'),
            completion_tokens=models.Sum('completion_tokens'),
        ).order_by('-cost')

        service_labels = dict(ServiceType.choices)

        for row in service_stats:
            service = row['service']
            label = service_labels.get(service, service)
            cost = row['cost'] or Decimal('0')
            requests = row['requests'] or 0

            self.stdout.write(f'\n  {label}')
            self.stdout.write(f'    Cost: ${cost:.6f}')
            self.stdout.write(f'    Requests: {requests}')

            if service == ServiceType.OPENROUTER:
                prompt = row['prompt_tokens'] or 0
                completion = row['completion_tokens'] or 0
                total = row['tokens'] or 0
                self.stdout.write(f'    Tokens: {total:,} (prompt: {prompt:,}, completion: {completion:,})')
            elif service in [ServiceType.ELEVENLABS_TTS, ServiceType.OPENAI_TTS]:
                chars = row['chars'] or 0
                self.stdout.write(f'    Characters: {chars:,}')
            elif service == ServiceType.DEEPGRAM_STT:
                audio = row['audio'] or 0
                minutes = audio / 60
                self.stdout.write(f'    Audio: {audio:.1f}s ({minutes:.2f} min)')
            elif service == ServiceType.BRAVE_SEARCH:
                self.stdout.write(f'    Searches: {requests}')

        # By Feature
        self.stdout.write(f'\n\n{self.style.HTTP_INFO("BY FEATURE:")}')
        self.stdout.write('-' * 50)

        feature_stats = query.values('feature').annotate(
            cost=models.Sum('cost_usd'),
            requests=models.Count('id'),
        ).order_by('-cost')

        feature_labels = dict(FeatureType.choices)

        for row in feature_stats:
            feature = row['feature']
            label = feature_labels.get(feature, feature)
            cost = row['cost'] or Decimal('0')
            requests = row['requests'] or 0

            self.stdout.write(f'\n  {label}')
            self.stdout.write(f'    Cost: ${cost:.6f}')
            self.stdout.write(f'    Requests: {requests}')

        # By Model (for OpenRouter)
        openrouter_logs = query.filter(service=ServiceType.OPENROUTER)
        if openrouter_logs.exists():
            self.stdout.write(f'\n\n{self.style.HTTP_INFO("OPENROUTER BY MODEL:")}')
            self.stdout.write('-' * 50)

            model_stats = openrouter_logs.values('model_id').annotate(
                cost=models.Sum('cost_usd'),
                requests=models.Count('id'),
                tokens=models.Sum('total_tokens'),
                prompt_tokens=models.Sum('prompt_tokens'),
                completion_tokens=models.Sum('completion_tokens'),
            ).order_by('-cost')

            for row in model_stats:
                model = row['model_id'] or 'unknown'
                cost = row['cost'] or Decimal('0')
                requests = row['requests'] or 0
                tokens = row['tokens'] or 0

                self.stdout.write(f'\n  {model}')
                self.stdout.write(f'    Cost: ${cost:.6f}')
                self.stdout.write(f'    Requests: {requests}')
                self.stdout.write(f'    Tokens: {tokens:,}')

        # Recent activity
        self.stdout.write(f'\n\n{self.style.HTTP_INFO("RECENT ACTIVITY (last 10):")}')
        self.stdout.write('-' * 50)

        recent = query.order_by('-timestamp')[:10]
        for log in recent:
            service_label = service_labels.get(log.service, log.service)
            self.stdout.write(
                f'  {log.timestamp.strftime("%Y-%m-%d %H:%M")} | '
                f'{service_label:15} | ${log.cost_usd:.6f} | '
                f'{log.model_id or log.feature}'
            )

        # Current quota status
        if subscription:
            self.stdout.write(f'\n\n{self.style.HTTP_INFO("CURRENT QUOTA STATUS:")}')
            self.stdout.write('-' * 50)

            quota_service = get_quota_service()
            quota_info = quota_service.get_user_quota_info(user)

            weekly_pct = (quota_info.weekly_used_usd / quota_info.weekly_limit_usd * 100) if quota_info.weekly_limit_usd else 0
            session_pct = (quota_info.session_used_usd / quota_info.session_limit_usd * 100) if quota_info.session_limit_usd else 0

            self.stdout.write('\n  Weekly:')
            self.stdout.write(f'    Used: ${quota_info.weekly_used_usd:.6f} / ${quota_info.weekly_limit_usd:.2f} ({weekly_pct:.1f}%)')
            self.stdout.write(f'    Remaining: ${quota_info.weekly_remaining_usd:.6f}')

            self.stdout.write('\n  Session:')
            self.stdout.write(f'    Used: ${quota_info.session_used_usd:.6f} / ${quota_info.session_limit_usd:.2f} ({session_pct:.1f}%)')
            self.stdout.write(f'    Remaining: ${quota_info.session_remaining_usd:.6f}')

        self.stdout.write(f'\n{"="*60}\n')
