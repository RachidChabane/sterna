"""
Billable Operation Decorators.

Provides decorators for automatically tracking billable operations.
Handles pre-flight quota checks and post-operation usage recording.
"""

import logging
from decimal import Decimal
from functools import wraps
from typing import Callable, Optional, TypeVar, Any

from usage_quota.billing.operations import BillableOperation
from usage_quota.billing.service import get_billing_service
from usage_quota.models import ServiceType, FeatureType
from usage_quota.exceptions import QuotaExceededException

logger = logging.getLogger(__name__)

T = TypeVar('T')

# Type alias for operation extractor functions
OperationExtractor = Callable[..., BillableOperation]


def billable(
    service: ServiceType,
    feature: FeatureType = FeatureType.CHAT,
    pre_check: bool = False,
    estimated_cost_usd: Optional[Decimal] = None,
    extract_operation: Optional[OperationExtractor] = None,
):
    """
    Decorator for billable operations.

    Automatically handles quota checking and usage recording for any function
    that performs a billable operation.

    Args:
        service: The billable service type (from ServiceType enum)
        feature: The feature consuming quota (from FeatureType enum)
        pre_check: If True, check quota before operation execution
        estimated_cost_usd: Estimated cost for pre-check (required if pre_check=True)
        extract_operation: Function to extract BillableOperation from the result.
                          Signature: (result, *args, **kwargs) -> BillableOperation
                          If not provided, usage won't be recorded (only pre-check)

    Usage:
        # Simple usage - just pre-check
        @billable(
            service=ServiceType.OPENROUTER,
            feature=FeatureType.CHAT,
            pre_check=True,
            estimated_cost_usd=Decimal('0.01'),
        )
        def my_llm_call(request, prompt: str) -> str:
            return call_llm(prompt)

        # With usage recording
        @billable(
            service=ServiceType.OPENROUTER,
            feature=FeatureType.CHAT,
            extract_operation=lambda result, **kw: BillableOperation(
                service=ServiceType.OPENROUTER,
                feature=FeatureType.CHAT,
                model_id=kw.get('model_id', ''),
                prompt_tokens=result.get('usage', {}).get('prompt_tokens', 0),
                completion_tokens=result.get('usage', {}).get('completion_tokens', 0),
                cost_usd=Decimal(str(result.get('cost', 0))),
            )
        )
        def complete_chat(request, model_id: str, messages: list) -> dict:
            return llm_response

    Raises:
        QuotaExceededException: If pre_check=True and quota is exceeded
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args, **kwargs) -> T:
            # Extract user from request object
            user = _extract_user(args, kwargs)
            if not user:
                logger.warning(
                    f"No user found for billable operation {func.__name__}, "
                    f"skipping billing"
                )
                return func(*args, **kwargs)

            billing = get_billing_service()

            # Pre-flight quota check
            if pre_check:
                cost = estimated_cost_usd or Decimal('0.01')
                status = billing.check_quota(user, service, cost, feature)
                if not status.allowed:
                    raise QuotaExceededException(
                        limit_type=status.denial_reason or "quota",
                        limit_usd=status.weekly_limit_usd if status.denial_reason == "weekly" else status.session_limit_usd,
                        used_usd=status.weekly_used_usd if status.denial_reason == "weekly" else status.session_used_usd,
                        remaining_usd=status.weekly_remaining_usd if status.denial_reason == "weekly" else status.session_remaining_usd,
                        resets_in_seconds=status.weekly_resets_in_seconds if status.denial_reason == "weekly" else status.session_resets_in_seconds,
                    )

            # Execute the operation
            result = func(*args, **kwargs)

            # Record usage if extractor provided
            if extract_operation is not None:
                try:
                    operation = extract_operation(result, *args, **kwargs)
                    billing.record_usage(user, operation)
                except Exception as e:
                    logger.error(
                        f"Failed to extract/record billable operation from "
                        f"{func.__name__}: {e}"
                    )

            return result

        return wrapper
    return decorator


def billable_async(
    service: ServiceType,
    feature: FeatureType = FeatureType.CHAT,
    pre_check: bool = False,
    estimated_cost_usd: Optional[Decimal] = None,
    extract_operation: Optional[OperationExtractor] = None,
):
    """
    Async version of @billable decorator.

    Same functionality as @billable but for async functions.
    See @billable for full documentation.
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            user = _extract_user(args, kwargs)
            if not user:
                logger.warning(
                    f"No user found for billable operation {func.__name__}, "
                    f"skipping billing"
                )
                return await func(*args, **kwargs)

            billing = get_billing_service()

            # Pre-flight quota check
            if pre_check:
                cost = estimated_cost_usd or Decimal('0.01')
                status = billing.check_quota(user, service, cost, feature)
                if not status.allowed:
                    raise QuotaExceededException(
                        limit_type=status.denial_reason or "quota",
                        limit_usd=status.weekly_limit_usd if status.denial_reason == "weekly" else status.session_limit_usd,
                        used_usd=status.weekly_used_usd if status.denial_reason == "weekly" else status.session_used_usd,
                        remaining_usd=status.weekly_remaining_usd if status.denial_reason == "weekly" else status.session_remaining_usd,
                        resets_in_seconds=status.weekly_resets_in_seconds if status.denial_reason == "weekly" else status.session_resets_in_seconds,
                    )

            # Execute the operation
            result = await func(*args, **kwargs)

            # Record usage if extractor provided
            if extract_operation is not None:
                try:
                    operation = extract_operation(result, *args, **kwargs)
                    billing.record_usage(user, operation)
                except Exception as e:
                    logger.error(
                        f"Failed to extract/record billable operation from "
                        f"{func.__name__}: {e}"
                    )

            return result

        return wrapper
    return decorator


def _extract_user(args: tuple, kwargs: dict) -> Optional[Any]:
    """
    Extract user from function arguments.

    Looks for user in common patterns:
    1. 'user' keyword argument
    2. 'request' keyword argument with .user attribute
    3. First positional argument with .user attribute (common for views)
    4. First positional argument that looks like a user (has id and email)

    Args:
        args: Positional arguments
        kwargs: Keyword arguments

    Returns:
        User object or None if not found
    """
    # Check kwargs first
    if 'user' in kwargs:
        return kwargs['user']

    if 'request' in kwargs:
        request = kwargs['request']
        if hasattr(request, 'user') and request.user and hasattr(request.user, 'id'):
            return request.user

    # Check positional args
    for arg in args:
        # Skip 'self' (common first arg in methods)
        if arg is None:
            continue

        # Check if it's a request object
        if hasattr(arg, 'user'):
            user = arg.user
            if user and hasattr(user, 'id'):
                return user

        # Check if it looks like a user object directly
        if hasattr(arg, 'id') and hasattr(arg, 'email'):
            return arg

    return None


# Convenience decorators for common service types
def billable_llm(
    feature: FeatureType = FeatureType.CHAT,
    pre_check: bool = False,
    estimated_cost_usd: Optional[Decimal] = None,
    extract_operation: Optional[OperationExtractor] = None,
):
    """Decorator for OpenRouter LLM operations."""
    return billable(
        service=ServiceType.OPENROUTER,
        feature=feature,
        pre_check=pre_check,
        estimated_cost_usd=estimated_cost_usd,
        extract_operation=extract_operation,
    )


def billable_tts(
    provider: str = 'elevenlabs',
    feature: FeatureType = FeatureType.VOICE_ROOM,
    pre_check: bool = False,
    estimated_cost_usd: Optional[Decimal] = None,
    extract_operation: Optional[OperationExtractor] = None,
):
    """Decorator for TTS operations (ElevenLabs or OpenAI)."""
    service = ServiceType.ELEVENLABS_TTS if provider == 'elevenlabs' else ServiceType.OPENAI_TTS
    return billable(
        service=service,
        feature=feature,
        pre_check=pre_check,
        estimated_cost_usd=estimated_cost_usd,
        extract_operation=extract_operation,
    )


def billable_stt(
    feature: FeatureType = FeatureType.VOICE_ROOM,
    pre_check: bool = False,
    estimated_cost_usd: Optional[Decimal] = None,
    extract_operation: Optional[OperationExtractor] = None,
):
    """Decorator for Deepgram STT operations."""
    return billable(
        service=ServiceType.DEEPGRAM_STT,
        feature=feature,
        pre_check=pre_check,
        estimated_cost_usd=estimated_cost_usd,
        extract_operation=extract_operation,
    )


def billable_search(
    feature: FeatureType = FeatureType.CHAT,
    pre_check: bool = False,
    estimated_cost_usd: Optional[Decimal] = None,
    extract_operation: Optional[OperationExtractor] = None,
):
    """Decorator for Brave Search operations."""
    return billable(
        service=ServiceType.BRAVE_SEARCH,
        feature=feature,
        pre_check=pre_check,
        estimated_cost_usd=estimated_cost_usd,
        extract_operation=extract_operation,
    )
