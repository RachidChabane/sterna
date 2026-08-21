"""Assembly of the upstream chat client the agent streams from.

Factory. Two steps, kept separate because the first one's output
(``extra_body``) is also stored on the agent as ``reasoning_config`` and
read later by the Direct Client path:

1. ``build_extra_body`` -- the OpenRouter-only request extras (reasoning
   object, output modalities, caller kwargs).
2. ``create_chat_model`` -- the ``ChatOpenAI`` instance itself.

Everything here is gated on ``is_openrouter``: direct provider endpoints
reject OpenRouter-specific parameters and attribution headers.
"""

import logging
from typing import Any, Dict, List, Optional

from django.conf import settings
from langchain_openai import ChatOpenAI

# Child of the configured "llm" logger (see sterna/logging.py APP_LOGGERS).
logger = logging.getLogger(__name__)

# Models that budget reasoning in tokens rather than in an effort level.
TOKEN_LIMITED_REASONING_MODEL_MARKERS = ('anthropic', 'claude', 'gemini', 'qwen')
# Reasoning budget used when the UI sent neither an effort nor a token cap.
DEFAULT_REASONING_MAX_TOKENS = 4000
# OpenRouter attribution headers (rejected by direct provider endpoints).
OPENROUTER_ATTRIBUTION_TITLE = "Sterna AI"
DEFAULT_FRONTEND_URL = 'http://localhost:5173'


def _build_reasoning_object(
    model: str,
    max_tokens: int,
    reasoning_effort: Optional[str],
    reasoning_max_tokens: Optional[int],
) -> Dict[str, Any]:
    """Build the OpenRouter `reasoning` object for this model.

    Different models use different parameters:
    - Effort-based models (OpenAI o-series, Grok): use "effort"
    - Token-limited models (Anthropic, Gemini, Qwen): use "max_tokens"
    """
    reasoning_obj: Dict[str, Any] = {}

    # Prioritize explicit parameters from UI
    if reasoning_max_tokens:
        reasoning_obj["max_tokens"] = reasoning_max_tokens
        logger.info(f"[LangChain] 🧠 Using reasoning_max_tokens={reasoning_max_tokens} from UI")
    elif reasoning_effort:
        reasoning_obj["effort"] = reasoning_effort
        logger.info(f"[LangChain] 🧠 Using reasoning_effort={reasoning_effort} from UI")
    else:
        # Auto-detect based on model type
        is_token_limited = any(
            marker in model.lower() for marker in TOKEN_LIMITED_REASONING_MODEL_MARKERS
        )
        if is_token_limited:
            # For Anthropic: use max_tokens (minimum 1024, maximum 32000)
            reasoning_obj["max_tokens"] = DEFAULT_REASONING_MAX_TOKENS
            logger.info("[LangChain] 🧠 Auto-detected token-limited model, using max_tokens=4000")
        else:
            reasoning_obj["enabled"] = True
            logger.info("[LangChain] 🧠 Using reasoning enabled=true")

    # CRITICAL: Set exclude=false to ensure reasoning is returned in response
    # Otherwise OpenRouter generates reasoning but doesn't send it back
    reasoning_obj["exclude"] = False

    # WARNING: For Anthropic, max_tokens (response) must be > reasoning.max_tokens
    # Ensure we have enough room for the actual response after reasoning
    if "max_tokens" in reasoning_obj and max_tokens <= reasoning_obj["max_tokens"]:
        logger.warning(f"[LangChain] ⚠️  max_tokens ({max_tokens}) should be > reasoning.max_tokens ({reasoning_obj['max_tokens']})")
        logger.warning("[LangChain] ⚠️  Model may fail or not have room for response after reasoning")

    return reasoning_obj


def build_extra_body(
    *,
    model: str,
    is_openrouter: bool,
    provider_slug: Optional[str],
    enable_reasoning: bool,
    max_tokens: int,
    reasoning_effort: Optional[str],
    reasoning_max_tokens: Optional[int],
    supports_image_output: bool,
    output_modalities: List[str],
    extra_kwargs: Dict[str, Any],
) -> Dict[str, Any]:
    """OpenRouter-specific request extras (`extra_body`) for this agent.

    `extra_body` carries custom parameters that aren't in OpenAI's API
    spec. OpenRouter-only parameters must not be sent to direct provider
    endpoints (they reject unknown params) — hence the `is_openrouter`
    gates.
    """
    extra_body: Dict[str, Any] = {}

    if enable_reasoning and not is_openrouter:
        logger.info(
            "[BYOK] Reasoning extras skipped for direct provider call "
            f"(provider={provider_slug})"
        )
    if enable_reasoning and is_openrouter:
        extra_body["reasoning"] = _build_reasoning_object(
            model=model,
            max_tokens=max_tokens,
            reasoning_effort=reasoning_effort,
            reasoning_max_tokens=reasoning_max_tokens,
        )

    # Add any additional kwargs to extra_body
    extra_body.update(extra_kwargs)

    # Add modalities for image generation models (OpenRouter-only —
    # image generation stays on OpenRouter in V1)
    if supports_image_output and is_openrouter:
        extra_body["modalities"] = output_modalities
        logger.info(f"[ImageGen] Enabled image generation with modalities: {output_modalities}")

    # Log reasoning configuration
    if enable_reasoning:
        logger.info(f"[LangChain] 🧠 Reasoning enabled with extra_body: {extra_body}")

    return extra_body


def create_chat_model(
    *,
    request_model: str,
    api_key: str,
    base_url: str,
    is_openrouter: bool,
    temperature: float,
    max_tokens: int,
    extra_body: Dict[str, Any],
) -> ChatOpenAI:
    """Instantiate the streaming ChatOpenAI client for this agent.

    IMPORTANT: ChatOpenAI expects extra_body as a direct parameter, NOT in
    model_kwargs. model_kwargs is for OpenAI-compatible params (like
    temperature, top_p); extra_body is for provider-specific params (like
    OpenRouter's reasoning).
    """
    llm_params: Dict[str, Any] = {
        "model": request_model,
        "openai_api_key": api_key,
        "openai_api_base": base_url,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "streaming": True,
        "stream_usage": True,  # Enable usage metadata in streaming chunks
    }
    # OpenRouter attribution headers must NOT be sent to direct
    # provider endpoints.
    if is_openrouter:
        llm_params["default_headers"] = {
            "HTTP-Referer": getattr(settings, 'FRONTEND_URL', DEFAULT_FRONTEND_URL),
            "X-Title": OPENROUTER_ATTRIBUTION_TITLE,
        }

    # Add extra_body directly as a parameter (not in model_kwargs)
    if extra_body:
        llm_params["extra_body"] = extra_body

    # Log configuration for debugging
    logger.info(f"[LangChain] Created ChatOpenAI with extra_body: {extra_body}")

    return ChatOpenAI(**llm_params)
