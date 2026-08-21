"""
LLM Services.

Centralized services for OpenRouter API key management, resolution, and usage tracking.
"""

from .openrouter_keys import (
    OpenRouterKeyService,
    OpenRouterKeyError,
    KeyUsageStats,
    get_key_service,
)
from .api_key_resolver import (
    APIKeyResolver,
    get_resolver,
    get_api_key,
    get_api_key_for_user,
    get_api_key_with_fallback,
)
from .usage_tracker import (
    UsageTracker,
    get_tracker,
    log_usage,
)
from .coding_agent_service import (
    CodingAgentService,
    CodingAgentJob,
    CodingAgentJobStatus,
    CodingAgentResult,
    CodingAgentStep,
    get_coding_agent_service,
    execute_coding_agent,
)

__all__ = [
    # Key provisioning
    'OpenRouterKeyService',
    'OpenRouterKeyError',
    'KeyUsageStats',
    'get_key_service',
    # Key resolution
    'APIKeyResolver',
    'get_resolver',
    'get_api_key',
    'get_api_key_for_user',
    'get_api_key_with_fallback',
    # Usage tracking
    'UsageTracker',
    'get_tracker',
    'log_usage',
    # Coding Agent
    'CodingAgentService',
    'CodingAgentJob',
    'CodingAgentJobStatus',
    'CodingAgentResult',
    'CodingAgentStep',
    'get_coding_agent_service',
    'execute_coding_agent',
]
