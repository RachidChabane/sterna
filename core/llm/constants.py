"""
Constants for LLM module.
"""

# Model Tiers
MODEL_TIERS = {
    "budget": {
        "models": [
            "openai/gpt-3.5-turbo",
            "anthropic/claude-instant-1.2",
            "google/gemini-flash",
            "meta-llama/llama-3-8b-instruct",
        ],
        "cost_estimate": 0.001,  # Per request estimate in USD
    },
    "balanced": {
        "models": [
            "openai/gpt-4-turbo-preview",
            "anthropic/claude-3-haiku",
            "google/gemini-pro",
            "mistralai/mixtral-8x7b-instruct",
        ],
        "cost_estimate": 0.01,
    },
    "quality": {
        "models": [
            "openai/gpt-4",
            "anthropic/claude-3-opus",
            "google/gemini-ultra",
            "openai/gpt-4-32k",
        ],
        "cost_estimate": 0.05,
    },
}

# Default configurations
DEFAULT_TEMPERATURE = 0.7
DEFAULT_MAX_TOKENS = 1000
DEFAULT_TOP_P = 1.0

# Rate limiting
DEFAULT_RATE_LIMIT = 100  # requests per minute
DEFAULT_BURST_SIZE = 20  # burst capacity

# Cache settings
MODEL_CATALOG_CACHE_TTL = 86400  # 24 hours in seconds

# Providers blacklist (never exposed to frontend)
# These providers should be filtered out from all API responses
BLACKLISTED_PROVIDERS = [
    'openrouter',  # OpenRouter is the API gateway, not a provider to expose
    'switchpoint',  # Switchpoint should not be exposed
]

# Retry settings
MAX_RETRIES = 3
RETRY_BACKOFF_BASE = 2
RETRY_BACKOFF_MAX = 60  # seconds

# Extended Search limits (Brave Search tools)
# Maximum number of Extended Search tool calls (brave_web_search, brave_news_search) allowed per message
# This prevents models from entering infinite loops when they don't understand search results
# Note: This is different from Web Search (OpenRouter native :online suffix)
MAX_EXTENDED_SEARCHES_PER_MESSAGE = 3

# Tool execution timeout
# Maximum time (in seconds) allowed for a single tool execution
# After this timeout, the tool call is cancelled and returns an error
TOOL_EXECUTION_TIMEOUT_SECONDS = 300  # 5 minutes

# Coding Agent specific timeout
# The coding_agent tool runs Claude Code CLI which can take longer for complex tasks
# This allows up to 15 minutes for autonomous coding agent execution
CODING_AGENT_TIMEOUT_SECONDS = 900  # 15 minutes

# Tool execution heartbeat interval
# During long-running tool execution (e.g., video generation), heartbeats are sent
# to keep the SSE connection alive and prevent proxy/browser timeouts
TOOL_HEARTBEAT_INTERVAL_SECONDS = 10  # seconds between heartbeats

# =============================================================================
# V2 Architecture Feature Flags
# =============================================================================
# These flags control the gradual migration to the new V2 architecture:
# on-demand tool discovery (search_available_tools) instead of loading every
# tool into the system prompt up front, plus the layered/cached V2 prompt
# system, programmatic tool calling, and per-user MCP sandbox isolation.

# Enable Tool Discovery (Tool Search Tool pattern)
# When True, tools are loaded on-demand via search_available_tools
# When False, all tools are included in system prompt (legacy behavior)
ENABLE_TOOL_DISCOVERY = True  # V2 ENABLED

# Enable PTC (Programmatic Tool Calling)
# When True, allows LLM to generate code that orchestrates multiple tools
# When False, uses standard single-tool calling
ENABLE_PTC = True  # V2 ENABLED

# Enable MCP V2 (per-user sandbox isolation)
# When True, MCP servers run in isolated per-user containers
# When False, uses shared MCP server instances
ENABLE_MCP_V2 = True  # V2 ENABLED
