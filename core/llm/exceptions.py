"""
Custom exceptions for LLM module.
"""

from typing import Optional


class LLMException(Exception):
    """Base exception for LLM module."""

    pass


class OpenRouterException(LLMException):
    """Exception for OpenRouter API errors."""

    pass


class ModelNotAvailableException(LLMException):
    """Exception when requested model is not available."""

    pass


class RateLimitException(LLMException):
    """Exception for rate limit violations."""

    pass


class InvalidResponseException(LLMException):
    """Exception for invalid or unparseable responses."""

    pass


class CostLimitException(LLMException):
    """Exception when cost limit is exceeded."""

    pass


class ContextLimitExceededException(LLMException):
    """Exception when conversation context exceeds model's maximum tokens."""

    def __init__(
        self,
        message: str,
        model_id: Optional[str] = None,
        required_tokens: Optional[int] = None,
        max_tokens: Optional[int] = None,
    ):
        """
        Initialize context limit exception with detailed information.

        Args:
            message: Human-readable error message
            model_id: ID of the model that has the limit
            required_tokens: Number of tokens required
            max_tokens: Maximum tokens supported by the model
        """
        super().__init__(message)
        self.model_id = model_id
        self.required_tokens = required_tokens
        self.max_tokens = max_tokens
