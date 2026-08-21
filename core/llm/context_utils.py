"""
Utilities for managing context limits and token calculations.

This module provides shared functionality for dynamically calculating max_tokens
based on model capabilities and prompt size, preventing context overflow errors.
"""

import logging
from typing import List, Dict

from .models import ModelCatalog
from .exceptions import ContextLimitExceededException

logger = logging.getLogger(__name__)


def estimate_tokens_from_messages(messages: List[Dict[str, str]]) -> int:
    """
    Estimate the number of tokens in a list of messages.

    Uses a rough approximation: 1 token ≈ 4 characters.

    Args:
        messages: List of message dictionaries with 'role' and 'content' keys

    Returns:
        Estimated number of tokens
    """
    total_chars = 0
    for msg in messages:
        # Include role in estimation (adds ~1-2 tokens per message)
        total_chars += len(msg.get('role', ''))
        total_chars += len(msg.get('content', ''))

    # Rough estimation: 1 token ≈ 4 characters
    # Add overhead for message formatting (role labels, delimiters, etc.)
    estimated_tokens = (total_chars // 4) + (len(messages) * 5)

    return estimated_tokens


def calculate_dynamic_max_tokens(
    model_id: str,
    messages: List[Dict[str, str]],
    configured_max_tokens: int,
    safety_margin: int = 2000,
    min_viable_tokens: int = 500
) -> int:
    """
    Calculate dynamic max_tokens based on model's context limit and prompt size.

    This function ensures that the total tokens (prompt + completion) don't exceed
    the model's maximum context length. It adjusts max_tokens dynamically based on:
    - Model's maximum context length
    - Estimated prompt size
    - Configured maximum tokens desired
    - Safety margin for estimation errors

    Args:
        model_id: The model identifier
        messages: List of messages that will be sent to the model
        configured_max_tokens: The desired max_tokens from configuration
        safety_margin: Extra tokens reserved for estimation errors (default: 2000)
        min_viable_tokens: Minimum tokens required for a meaningful response (default: 500)

    Returns:
        Adjusted max_tokens value that fits within model's context limit

    Raises:
        ContextLimitExceededException: If prompt is too large for the model
    """
    # Get model info from catalog
    # Strip OpenRouter suffixes (:thinking, :online, etc.) for catalog lookup
    base_model_id = model_id.split(':')[0] if ':' in model_id else model_id

    try:
        model_info = ModelCatalog.objects.get(model_id=base_model_id)
        model_max_tokens = model_info.max_tokens or 32768  # Default to 32k if not specified
        model_name = model_info.name
    except ModelCatalog.DoesNotExist:
        logger.warning(f"Model {base_model_id} not found in catalog, using default limits")
        model_max_tokens = 32768
        model_name = model_id

    # Estimate prompt tokens
    estimated_prompt_tokens = estimate_tokens_from_messages(messages)

    # Calculate available tokens for completion
    available_for_completion = model_max_tokens - estimated_prompt_tokens - safety_margin

    # Check if we have enough room for a meaningful response
    if available_for_completion < min_viable_tokens:
        error_msg = (
            f"Conversation is too long for model '{model_name}' (context limit: {model_max_tokens:,} tokens). "
            f"Estimated prompt size: ~{estimated_prompt_tokens:,} tokens, "
            f"available for response: ~{available_for_completion:,} tokens. "
            f"Please use a model with larger context window or reduce conversation length."
        )
        logger.error(error_msg)
        raise ContextLimitExceededException(
            error_msg,
            model_id=model_id,
            required_tokens=estimated_prompt_tokens + min_viable_tokens,
            max_tokens=model_max_tokens
        )

    # Calculate actual max_tokens: minimum of configured and available
    actual_max_tokens = min(configured_max_tokens, available_for_completion)

    logger.info(
        f"Dynamic max_tokens calculation: model={model_id}, "
        f"context_limit={model_max_tokens:,}, estimated_prompt={estimated_prompt_tokens:,}, "
        f"configured_max={configured_max_tokens:,}, actual_max={actual_max_tokens:,}"
    )

    return actual_max_tokens
