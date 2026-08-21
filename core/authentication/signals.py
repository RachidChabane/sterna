"""
Authentication signals.

Handles user lifecycle events like registration to provision
OpenRouter API keys and perform other setup tasks.
"""

import logging
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.conf import settings

from .models import User

logger = logging.getLogger(__name__)


@receiver(post_save, sender=User)
def provision_openrouter_key_on_create(sender, instance, created, **kwargs):
    """
    Provision an OpenRouter API key when a new user is created.

    This ensures each user has their own API key for usage tracking
    and billing purposes.

    Note: If provisioning fails, user registration still succeeds.
    The key can be provisioned later via admin action or background task.
    """
    if not created:
        return

    # Skip if user already has a key (e.g., from migration or manual setup)
    if instance.openrouter_api_key:
        return

    # Check if provisioning is enabled
    provisioning_key = getattr(settings, 'OPENROUTER_PROVISIONING_KEY', '')
    if not provisioning_key:
        logger.debug(
            f"Skipping OpenRouter key provisioning for user {instance.id}: "
            "OPENROUTER_PROVISIONING_KEY not configured"
        )
        return

    # Import here to avoid circular imports
    from llm.services.openrouter_keys import get_key_service, OpenRouterKeyError

    try:
        service = get_key_service()
        service.provision_key_for_user(instance)
        logger.info(f"Provisioned OpenRouter key for new user {instance.id}")
    except OpenRouterKeyError as e:
        logger.error(
            f"Failed to provision OpenRouter key for user {instance.id}: {e}"
        )
        # Don't fail user registration - they can still use the system
        # with the fallback API key. Key can be provisioned later.
    except Exception as e:
        logger.exception(
            f"Unexpected error provisioning key for user {instance.id}: {e}"
        )


@receiver(post_save, sender=User)
def enqueue_stripe_customer_on_create(sender, instance, created, **kwargs):
    """Schedule a Stripe Customer for every new user (task 11).

    Both email/password signup (RegisterView) and OAuth signup
    (allauth social_login) emit ``post_save(created=True)`` on
    ``User``, so this single signal covers both paths.

    The actual API call happens in the ``ensure_stripe_customer``
    Celery task. Skipping at the signal level is intentional: signup
    must not block on Stripe's response time.
    """
    if not created:
        return
    if instance.stripe_customer_id:
        return

    from usage_quota.tasks import ensure_stripe_customer

    try:
        ensure_stripe_customer.delay(str(instance.id))
    except Exception as e:
        logger.warning(
            "ensure_stripe_customer dispatch failed for user %s: %s",
            instance.id,
            e,
        )
