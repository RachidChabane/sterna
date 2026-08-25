"""The model description a file a tool writes is attributed to.

A file produced during a turn is stored with the model that produced
it, so the frontend can label and badge it later. That description is
assembled from the catalog row plus the icon slugs the rest of the app
resolves the same names through, and reaches the tool implementations
on the file-tools context.

A turn with no file tools stores nothing, and a model the catalog does
not hold has nothing to describe, so both are answered with no
description at all.
"""

import logging
from typing import Any, Dict, Optional

from ..icon_utils import get_model_icon_slug, get_provider_icon_slug

# Child of the configured "llm" logger (see sterna/logging.py APP_LOGGERS).
logger = logging.getLogger(__name__)

NAME_FIELD = "name"
ID_FIELD = "id"
PROVIDER_FIELD = "provider"


def build_model_metadata(
    model_row: Optional[Dict[str, Any]],
    *,
    file_tools_enabled: bool,
    message_id: Optional[str],
) -> Optional[Dict[str, Any]]:
    """How a file this turn writes is attributed, or `None` when nothing is."""

    if not file_tools_enabled or not model_row:
        return None
    try:
        model_name = model_row.get(NAME_FIELD)
        model_id = model_row.get(ID_FIELD)
        provider = model_row.get(PROVIDER_FIELD)
        metadata = {
            "model_name": model_name,
            "model_id": model_id,
            "provider": provider,
            "model_icon_slug": get_model_icon_slug(model_id, model_name),
            "model_icon_url": None,
            "provider_icon_slug": get_provider_icon_slug(provider),
            "provider_icon_url": None,
            "message_id": message_id,
        }
        logger.info(f"[LangChain] Model metadata: {metadata}")
        return metadata
    except Exception as e:
        logger.warning(f"[LangChain] Failed to get model metadata: {e}")
        return None
