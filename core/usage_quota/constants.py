"""Shared constants for the usage_quota app.

`OPENROUTER_BACKED_SERVICES` is the "may-bypass" guard for BYOK billing:
only services in this set may carry billing_origin='byok' at the
BillingService layer. Any other service forcing 'byok' is an OPS bug and
raises BillingMisconfiguration.

NOTE on IMAGE_GENERATION: this ServiceType is mixed-provider (OpenRouter
+ Google AI Studio). Membership here authorizes BYOK *only when the
provider is OpenRouter* — Google AI Studio always pays platform. The
billing layer cannot distinguish the two at the ServiceType level, so
call-site enforcement is required:
  - `core/llm/image_tools.py:_record_billing` (Google AI Studio path)
    hard-codes billing_origin='platform'.
  - The OpenRouter image-gen path is billed via langchain_agent.py's
    accumulated_tool_cost path, which uses the resolved request origin.
If a future caller forces billing_origin='byok' on an IMAGE_GENERATION
op produced by Google AI Studio, the guard will NOT catch it.
"""

from usage_quota.models import ServiceType


OPENROUTER_BACKED_SERVICES: frozenset[str] = frozenset({
    ServiceType.OPENROUTER.value,
    ServiceType.KNOWLEDGE_BASE_EMBEDDING.value,
    ServiceType.KNOWLEDGE_BASE_QUERY.value,
    ServiceType.IMAGE_GENERATION.value,
    ServiceType.CODE_SESSION.value,
    ServiceType.MCP_TOOL_INVOCATION.value,
})


PLATFORM_ONLY_SERVICES: frozenset[str] = frozenset({
    ServiceType.ELEVENLABS_TTS.value,
    ServiceType.OPENAI_TTS.value,
    ServiceType.DEEPGRAM_STT.value,
    ServiceType.BRAVE_SEARCH.value,
    ServiceType.GOOGLE_MAPS.value,
    ServiceType.VIDEO_GENERATION.value,
})


BillingOrigin = str
BILLING_ORIGIN_BYOK = 'byok'
BILLING_ORIGIN_PLATFORM = 'platform'
VALID_BILLING_ORIGINS: frozenset[str] = frozenset({
    BILLING_ORIGIN_BYOK,
    BILLING_ORIGIN_PLATFORM,
})
