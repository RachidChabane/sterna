"""
Utility functions for LLM module.
"""

from django.db.models import Q, QuerySet
from .constants import BLACKLISTED_PROVIDERS


def exclude_blacklisted_providers(queryset: QuerySet) -> QuerySet:
    """
    Exclude blacklisted providers from queryset.

    Providers in BLACKLISTED_PROVIDERS should never be exposed to the frontend.
    This helper ensures consistent filtering across all endpoints.

    Args:
        queryset: Django QuerySet to filter

    Returns:
        Filtered QuerySet without blacklisted providers
    """
    if not BLACKLISTED_PROVIDERS:
        return queryset

    # Build Q object for case-insensitive exclusion
    exclude_query = Q()
    for provider in BLACKLISTED_PROVIDERS:
        exclude_query |= Q(provider__iexact=provider)

    return queryset.exclude(exclude_query)


def is_provider_blacklisted(provider: str) -> bool:
    """
    Check if a provider is blacklisted.

    Args:
        provider: Provider name to check

    Returns:
        True if provider is blacklisted, False otherwise
    """
    if not provider:
        return False

    return provider.lower() in [p.lower() for p in BLACKLISTED_PROVIDERS]
