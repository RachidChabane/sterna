"""Preserve the OpenRouter generation id inside LangChain stream chunks.

Monkey-patch (applied once, at import time). LangChain's
``_convert_chunk_to_generation_chunk`` discards ``chunk["id"]`` -- the
OpenRouter generation id -- which makes it impossible to query OpenRouter
for precise billing data after an interrupted stream. This module
re-attaches it under ``generation_info["openrouter_generation_id"]``.

Importing this module more than once is harmless: ``_apply`` is guarded so
the original function is never wrapped twice.
"""

import langchain_openai.chat_models.base as _lc_base

_PATCH_MARKER = "_sterna_preserves_openrouter_generation_id"


def _apply() -> None:
    original_convert = _lc_base._convert_chunk_to_generation_chunk
    if getattr(original_convert, _PATCH_MARKER, False):
        return

    def _patched_convert_chunk_to_generation_chunk(chunk, default_chunk_class, base_generation_info):
        result = original_convert(chunk, default_chunk_class, base_generation_info)
        if result is not None and chunk.get("id"):
            if result.generation_info is None:
                result.generation_info = {}
            result.generation_info["openrouter_generation_id"] = chunk["id"]
        return result

    setattr(_patched_convert_chunk_to_generation_chunk, _PATCH_MARKER, True)
    _lc_base._convert_chunk_to_generation_chunk = _patched_convert_chunk_to_generation_chunk


_apply()
