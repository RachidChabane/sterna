"""
OpenRouter Usage Tracking Service.

Provides centralized usage logging for all OpenRouter API calls.
This enables monitoring, billing, and analytics regardless of
where in the codebase the API is called.
"""

import logging
from typing import Optional, Dict, Any, TYPE_CHECKING
from decimal import Decimal


if TYPE_CHECKING:
    from authentication.models import User

logger = logging.getLogger(__name__)


class UsageTracker:
    """
    Tracks OpenRouter API usage for monitoring and billing.

    Usage:
        tracker = get_tracker()
        tracker.log_usage(
            user=request.user,
            model_id='openai/gpt-4',
            prompt_tokens=100,
            completion_tokens=50,
            cost_usd=0.0045,
            request_source='chat',
        )
    """

    def log_usage(
        self,
        user: Optional['User'],
        model_id: str,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        cost_usd: float = 0.0,
        request_source: str = 'unknown',
        endpoint: str = 'chat/completions',
        openrouter_request_id: Optional[str] = None,
        extra_data: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Log a single API usage event.

        Args:
            user: User who made the request (None for anonymous)
            model_id: Model used (e.g., 'openai/gpt-4')
            prompt_tokens: Number of prompt tokens
            completion_tokens: Number of completion tokens
            cost_usd: Cost in USD
            request_source: Where the request originated
            endpoint: API endpoint called
            openrouter_request_id: Request ID from OpenRouter
            extra_data: Additional metadata

        Returns:
            True if logged successfully, False otherwise
        """
        if not user or not hasattr(user, 'is_authenticated') or not user.is_authenticated:
            # Don't log anonymous usage to database
            logger.debug(
                f"Anonymous usage: {model_id} - "
                f"{prompt_tokens + completion_tokens} tokens - "
                f"${cost_usd:.6f}"
            )
            return True

        try:
            from llm.models import OpenRouterUsageLog

            OpenRouterUsageLog.objects.create(
                user=user,
                model_id=model_id,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens,
                cost_usd=Decimal(str(cost_usd)),
                endpoint=endpoint,
                request_source=request_source,
                openrouter_request_id=openrouter_request_id or '',
                extra_data=extra_data or {},
            )

            logger.debug(
                f"Logged usage for {user.email}: {model_id} - "
                f"{prompt_tokens + completion_tokens} tokens - "
                f"${cost_usd:.6f}"
            )
            return True

        except Exception as e:
            logger.warning(f"Failed to log usage: {e}")
            return False

    def get_user_usage_summary(
        self,
        user: 'User',
        days: int = 30,
    ) -> Dict[str, Any]:
        """
        Get usage summary for a user.

        Args:
            user: User to get summary for
            days: Number of days to include

        Returns:
            Dictionary with usage statistics
        """
        from django.db.models import Sum, Count
        from django.utils import timezone
        from datetime import timedelta
        from llm.models import OpenRouterUsageLog

        cutoff = timezone.now() - timedelta(days=days)

        logs = OpenRouterUsageLog.objects.filter(
            user=user,
            timestamp__gte=cutoff,
        )

        total = logs.aggregate(
            total_tokens=Sum('total_tokens'),
            total_cost=Sum('cost_usd'),
            total_requests=Count('id'),
        )

        by_model = logs.values('model_id').annotate(
            tokens=Sum('total_tokens'),
            cost=Sum('cost_usd'),
            requests=Count('id'),
        ).order_by('-cost')[:10]

        by_source = logs.values('request_source').annotate(
            tokens=Sum('total_tokens'),
            cost=Sum('cost_usd'),
            requests=Count('id'),
        ).order_by('-cost')

        return {
            'period_days': days,
            'total': {
                'tokens': total['total_tokens'] or 0,
                'cost': float(total['total_cost'] or 0),
                'requests': total['total_requests'] or 0,
            },
            'by_model': [
                {
                    'model_id': m['model_id'],
                    'tokens': m['tokens'] or 0,
                    'cost': float(m['cost'] or 0),
                    'requests': m['requests'] or 0,
                }
                for m in by_model
            ],
            'by_source': [
                {
                    'source': s['request_source'],
                    'tokens': s['tokens'] or 0,
                    'cost': float(s['cost'] or 0),
                    'requests': s['requests'] or 0,
                }
                for s in by_source
            ],
        }

    def get_global_usage_summary(self, days: int = 30) -> Dict[str, Any]:
        """
        Get global usage summary across all users.

        Args:
            days: Number of days to include

        Returns:
            Dictionary with global usage statistics
        """
        from django.db.models import Sum, Count
        from django.utils import timezone
        from datetime import timedelta
        from llm.models import OpenRouterUsageLog

        cutoff = timezone.now() - timedelta(days=days)

        logs = OpenRouterUsageLog.objects.filter(timestamp__gte=cutoff)

        total = logs.aggregate(
            total_tokens=Sum('total_tokens'),
            total_cost=Sum('cost_usd'),
            total_requests=Count('id'),
        )

        by_user = logs.values('user__email').annotate(
            tokens=Sum('total_tokens'),
            cost=Sum('cost_usd'),
            requests=Count('id'),
        ).order_by('-cost')[:20]

        by_model = logs.values('model_id').annotate(
            tokens=Sum('total_tokens'),
            cost=Sum('cost_usd'),
            requests=Count('id'),
        ).order_by('-cost')[:10]

        return {
            'period_days': days,
            'total': {
                'tokens': total['total_tokens'] or 0,
                'cost': float(total['total_cost'] or 0),
                'requests': total['total_requests'] or 0,
            },
            'by_user': [
                {
                    'email': u['user__email'],
                    'tokens': u['tokens'] or 0,
                    'cost': float(u['cost'] or 0),
                    'requests': u['requests'] or 0,
                }
                for u in by_user
            ],
            'by_model': [
                {
                    'model_id': m['model_id'],
                    'tokens': m['tokens'] or 0,
                    'cost': float(m['cost'] or 0),
                    'requests': m['requests'] or 0,
                }
                for m in by_model
            ],
        }


# Singleton instance
_tracker: Optional[UsageTracker] = None


def get_tracker() -> UsageTracker:
    """Get the singleton UsageTracker instance."""
    global _tracker
    if _tracker is None:
        _tracker = UsageTracker()
    return _tracker


def log_usage(
    user: Optional['User'],
    model_id: str,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    cost_usd: float = 0.0,
    request_source: str = 'unknown',
    **kwargs,
) -> bool:
    """Convenience function to log usage."""
    return get_tracker().log_usage(
        user=user,
        model_id=model_id,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        cost_usd=cost_usd,
        request_source=request_source,
        **kwargs,
    )
