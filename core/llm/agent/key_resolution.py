"""Endpoints and keys for work that is NOT the chat completion itself.

Resolver. A provider-scoped BYOK chat holds a key that only its own
provider accepts (an Anthropic key, say). Two side jobs still need to
reach elsewhere:

* the coding agent, which always runs against OpenRouter, and
* the 413 compaction summarizer, which runs a small OpenAI model.

Both resolve their own endpoint here rather than reusing the chat's key.
"""

import logging
from typing import Callable, Optional, Tuple

from asgiref.sync import sync_to_async

# Child of the configured "llm" logger (see sterna/logging.py APP_LOGGERS).
logger = logging.getLogger(__name__)


class EndpointKeyResolver:
    """Resolves API keys/endpoints for the agent's non-chat calls."""

    def __init__(
        self,
        *,
        resolve_user_id: Callable[[], Optional[str]],
        api_key: str,
        base_url: str,
        is_openrouter: bool,
        provider_slug: Optional[str],
    ):
        self._resolve_user_id = resolve_user_id
        self._api_key = api_key
        self._base_url = base_url
        self._is_openrouter = is_openrouter
        self._provider_slug = provider_slug

    async def _user(self):
        user_id = self._resolve_user_id()
        if not user_id:
            return None
        try:
            from authentication.models import User
            return await sync_to_async(User.objects.get)(id=user_id)
        except Exception:
            return None

    async def openrouter_key_for_tools(self) -> str:
        """OpenRouter-capable API key for non-chat tools (coding agent).

        Tools like the coding agent always run against OpenRouter (V1
        scope). When this chat is routed directly to a provider,
        self.api_key is a provider key that OpenRouter would reject —
        resolve the user's OpenRouter key (or platform fallback) instead.
        """
        if self._is_openrouter:
            return self._api_key

        from llm.services.api_key_resolver import get_resolver

        user = await self._user()
        try:
            key, _origin = await sync_to_async(get_resolver().resolve_with_origin)(
                user=user,
            )
            return key
        except ValueError:
            return self._api_key

    async def summarizer_endpoint(self, summarizer_model: str) -> Tuple[str, str, str]:
        """``(api_key, base_url, model)`` for the compaction summarizer.

        The agent's own api_key may be a provider-scoped key (e.g. an
        Anthropic key) that is useless for the OpenAI summarizer model —
        resolve the summarizer's endpoint independently so BYOK users
        with an 'openai' provider key go direct, and everyone else goes
        through OpenRouter as before.
        """
        from llm.provider_registry import native_model_name
        from llm.services.api_key_resolver import get_resolver

        user = await self._user()
        try:
            api_key, base_url, _origin, slug = await sync_to_async(
                get_resolver().resolve_endpoint
            )(user=user, model_id=summarizer_model)
        except ValueError:
            # No key anywhere — last resort: reuse the agent's own endpoint.
            model = (
                native_model_name(summarizer_model)
                if self._provider_slug
                else summarizer_model
            )
            return self._api_key, self._base_url, model
        model = native_model_name(summarizer_model) if slug else summarizer_model
        return api_key, base_url, model
