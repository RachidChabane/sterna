"""
User-friendly error message utilities for backend

Converts technical exceptions into user-friendly messages while preserving
technical details in server logs for debugging.
"""

import logging
from typing import Optional, Union

logger = logging.getLogger(__name__)

# Machine-readable error codes the frontend can act on (e.g. open the
# API-key settings). Only codes with a direct user resolution belong here.
ERROR_CODE_NO_API_KEY = 'no_api_key'
ERROR_CODE_INVALID_API_KEY = 'invalid_api_key'
ERROR_CODE_INSUFFICIENT_CREDITS = 'insufficient_credits'

_ACTIONABLE_MESSAGES = {
    ERROR_CODE_NO_API_KEY: (
        'You need an API key to use this model. '
        'Add a provider key or an OpenRouter key in Settings.'
    ),
    ERROR_CODE_INVALID_API_KEY: (
        'Your API key was rejected by the provider. '
        'Check it in Settings, or remove it to use a different key.'
    ),
    ERROR_CODE_INSUFFICIENT_CREDITS: (
        'Your API key has run out of credits. '
        'Top up with your provider, or switch keys in Settings.'
    ),
}


def get_error_code(exception: Union[Exception, str]) -> Optional[str]:
    """Map an exception to a machine-readable, user-actionable code.

    Returns None for errors with no direct user resolution (those keep
    the generic friendly message).
    """
    # Lazy import to avoid a cycle (api_key_resolver has no import of us,
    # but keep the coupling one-way regardless).
    from llm.services.api_key_resolver import NoAPIKeyError

    if isinstance(exception, NoAPIKeyError):
        return ERROR_CODE_NO_API_KEY

    error_str = str(exception).lower()

    if 'no openrouter api key available' in error_str or 'no api key available' in error_str:
        return ERROR_CODE_NO_API_KEY

    key_context = (
        'api key' in error_str
        or 'openrouter' in error_str
        or 'api.openai.com' in error_str
        or 'api.anthropic.com' in error_str
        or 'generativelanguage.googleapis.com' in error_str
        or 'api.mistral.ai' in error_str
        or 'api.deepseek.com' in error_str
        or 'api.x.ai' in error_str
        or 'chat/completions' in error_str
    )
    if key_context and ('401' in error_str or 'unauthorized' in error_str or 'invalid_api_key' in error_str):
        return ERROR_CODE_INVALID_API_KEY

    if key_context and (
        '402' in error_str
        or 'insufficient credits' in error_str
        or 'insufficient_quota' in error_str
        or 'payment required' in error_str
    ):
        return ERROR_CODE_INSUFFICIENT_CREDITS

    return None


def error_payload(exception: Union[Exception, str]) -> dict:
    """Build the SSE/API error payload: friendly message + optional code.

    The frontend uses ``code`` to render direct-resolution actions
    (open API-key settings) instead of a dead-end generic message.
    """
    code = get_error_code(exception)
    if code:
        return {'error': _ACTIONABLE_MESSAGES[code], 'code': code}
    return {'error': get_user_friendly_error(exception)}


def get_user_friendly_error(exception: Union[Exception, str]) -> str:
    """
    Convert technical exception to user-friendly message

    Args:
        exception: Exception or error string

    Returns:
        User-friendly error message without technical details
    """
    # Log the technical error for debugging
    logger.error(f"Technical error (converted to user-friendly message): {exception}", exc_info=True)

    # Actionable errors get their specific message everywhere, even on
    # call paths that don't propagate the machine code.
    code = get_error_code(exception)
    if code:
        return _ACTIONABLE_MESSAGES[code]

    # Convert to string for pattern matching
    error_str = str(exception).lower()

    # Never expose internal service URLs or provider names
    if 'openrouter' in error_str or 'api/v1/chat/completions' in error_str:
        # Extract just the HTTP status if present
        if '400' in error_str:
            return 'Unable to process your request. Please try again.'
        if '401' in error_str or 'unauthorized' in error_str:
            return 'Authentication error. Please check your settings.'
        if '429' in error_str:
            return 'Too many requests. Please wait a moment and try again.'
        return 'The AI service encountered an error. Please try again.'

    # Rate limiting
    if '429' in error_str or 'rate limit' in error_str or 'too many requests' in error_str:
        return 'Too many requests. Please wait a moment and try again.'

    # Network & HTTP errors
    if '400' in error_str or 'bad request' in error_str:
        return 'Unable to process your request. Please try again.'

    if '404' in error_str or 'not found' in error_str:
        return 'The AI service is temporarily unavailable. Please try again.'

    if '500' in error_str or 'server error' in error_str or 'internal server' in error_str:
        return 'The AI service encountered an error. Please try again later.'

    if '502' in error_str or 'bad gateway' in error_str:
        return 'The AI service is temporarily unavailable. Please try again.'

    if '503' in error_str or 'service unavailable' in error_str:
        return 'The AI service is temporarily unavailable. Please try again later.'

    if 'timeout' in error_str or 'timed out' in error_str:
        return 'The request took too long. Please try again.'

    if 'connection' in error_str or 'refused' in error_str:
        return 'Unable to connect to the AI service. Please try again.'

    # Authentication & Authorization
    if 'unauthorized' in error_str or '401' in error_str:
        return 'Please sign in to continue.'

    if 'forbidden' in error_str or '403' in error_str:
        return 'You don\'t have permission to perform this action.'

    # Model-specific errors
    if 'model not found' in error_str or 'model unavailable' in error_str:
        return 'This model is currently unavailable. Please try a different model.'

    if 'context' in error_str or 'token limit' in error_str or 'too long' in error_str:
        return 'Your message is too long. Please shorten it and try again.'

    # Quota & usage limit errors - pass through if already has reset time
    if 'resets' in error_str:
        # Already has reset time info, return as-is (capitalize first letter)
        return str(exception).strip().capitalize() if str(exception)[0].islower() else str(exception).strip()

    if 'session' in error_str and ('limit' in error_str or 'exceeded' in error_str):
        return 'Session limit reached. Please try again later.'

    if 'weekly' in error_str and ('limit' in error_str or 'exceeded' in error_str):
        return 'Weekly limit reached. Please try again later.'

    if 'quota' in error_str or 'usage limit' in error_str:
        return 'Usage limit reached. Please try again later.'

    # Generic fallback
    return 'Unable to process your request. Please try again.'


def sanitize_error_for_api(exception: Union[Exception, str]) -> dict:
    """
    Create a sanitized error response for API endpoints

    Args:
        exception: Exception or error string

    Returns:
        Dict with user-friendly error message (+ ``code`` when actionable)
    """
    return error_payload(exception)
