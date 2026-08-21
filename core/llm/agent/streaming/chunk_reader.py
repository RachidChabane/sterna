"""Reading the pieces of a LangChain `AIMessageChunk`.

Adapter over a loosely-typed streaming chunk. LangChain surfaces the same
payload under different attributes depending on provider and version
(`additional_kwargs` vs `response_metadata`, `tool_call_chunks` vs
`tool_calls`), so every access is defensive and lives here rather than in
the streaming loop.

All functions are pure/non-yielding: they read a chunk (or mutate an
accumulator dict) and return values for the loop to act on.
"""

import json
import logging
from typing import Any, Dict, List, Optional, Tuple

from ..thinking_parser import contains_tool_call_markers, REASONING_SNIPPET_CHARS

# Child of the configured "llm" logger (see sterna/logging.py APP_LOGGERS).
logger = logging.getLogger(__name__)

GENERATION_ID_METADATA_KEY = 'openrouter_generation_id'
REASONING_DETAILS_KEY = 'reasoning_details'
IMAGES_KEY = 'images'

REASONING_DETAIL_TEXT = 'reasoning.text'
REASONING_DETAIL_SUMMARY = 'reasoning.summary'
# reasoning.encrypted is skipped on purpose: it is protected content.

# Emit a heartbeat after this many chunks that produced no other event.
HEARTBEAT_CHUNK_INTERVAL = 5
# Depth of the reasoning-details diagnostic logging.
REASONING_DEBUG_CHUNK_LIMIT = 3


def _from_chunk_metadata(chunk, key: str):
    """Read `key` from additional_kwargs, falling back to response_metadata."""
    if hasattr(chunk, 'additional_kwargs') and chunk.additional_kwargs:
        value = chunk.additional_kwargs.get(key)
        if value:
            return value
    if hasattr(chunk, 'response_metadata') and chunk.response_metadata:
        return chunk.response_metadata.get(key)
    return None


def read_generation_id(chunk) -> Optional[str]:
    """The OpenRouter generation id preserved by our LangChain patch."""
    if hasattr(chunk, 'response_metadata') and chunk.response_metadata:
        return chunk.response_metadata.get(GENERATION_ID_METADATA_KEY)
    return None


def read_reasoning_details(chunk, chunk_count: int):
    """Raw `reasoning_details` list carried natively by OpenRouter, if any.

    OpenRouter sends reasoning in `choices[].delta.reasoning_details`;
    LangChain exposes it in `additional_kwargs['reasoning_details']` and,
    for some versions, in `response_metadata`.
    """
    reasoning_details = None
    if hasattr(chunk, 'additional_kwargs') and chunk.additional_kwargs:
        reasoning_details = chunk.additional_kwargs.get(REASONING_DETAILS_KEY)
        if reasoning_details and chunk_count <= REASONING_DEBUG_CHUNK_LIMIT:
            logger.info(f"[LangChain] 💭 Found reasoning_details in additional_kwargs: {reasoning_details}")
    if not reasoning_details and hasattr(chunk, 'response_metadata') and chunk.response_metadata:
        reasoning_details = chunk.response_metadata.get(REASONING_DETAILS_KEY)
        if reasoning_details and chunk_count <= REASONING_DEBUG_CHUNK_LIMIT:
            logger.info(f"[LangChain] 💭 Found reasoning_details in response_metadata: {reasoning_details}")
    return reasoning_details


def read_reasoning_detail_text(detail) -> Optional[str]:
    """Reasoning text carried by one `reasoning_details` entry.

    Returns None for entry types that carry no readable text (notably
    `reasoning.encrypted`, which is protected).
    """
    detail_type = detail.get('type', '')
    if detail_type == REASONING_DETAIL_TEXT:
        return detail.get('text', '')
    if detail_type == REASONING_DETAIL_SUMMARY:
        return detail.get('summary', '')
    return None


def is_tool_call_in_reasoning(reasoning_chunk: str) -> bool:
    """A tool call inside a native reasoning block: invalid, must abort."""
    if not contains_tool_call_markers(reasoning_chunk):
        return False
    logger.error(
        "langchain.tool_call_in_native_reasoning",
        extra={"reasoning_snippet": reasoning_chunk[:REASONING_SNIPPET_CHARS]},
    )
    return True


def read_images(chunk) -> List[Any]:
    """Generated images attached to this chunk (image-output models)."""
    return _from_chunk_metadata(chunk, IMAGES_KEY) or []


def accumulate_tool_call_chunks(chunk, tool_calls_dict: Dict[Any, Dict[str, str]]) -> None:
    """Fold one chunk's streamed tool-call fragments into the accumulator.

    IMPORTANT: keyed by `index`, not `id`, because only the first chunk of
    a tool call carries an id while `index` is stable across all of them.
    """
    for tc_chunk in chunk.tool_call_chunks:
        # tc_chunk may be a dict or an object with attributes
        if isinstance(tc_chunk, dict):
            tool_index = tc_chunk.get("index", 0)
            tool_id = tc_chunk.get("id")
            tool_name = tc_chunk.get("name", "")
            tool_args = tc_chunk.get("args", "")
        else:
            tool_index = getattr(tc_chunk, "index", 0)
            tool_id = getattr(tc_chunk, "id", None)
            tool_name = getattr(tc_chunk, "name", "")
            tool_args = getattr(tc_chunk, "args", "")

        accumulator = tool_calls_dict.setdefault(
            tool_index, {"id": None, "name": "", "args": ""}
        )
        if tool_id:
            accumulator["id"] = tool_id
        if tool_name:
            accumulator["name"] = tool_name
        # Args arrive in fragments like '{"a"', ': 3, ', ...
        if tool_args:
            accumulator["args"] += tool_args


def accumulate_complete_tool_calls(chunk, tool_calls_dict: Dict[Any, Dict[str, str]]) -> None:
    """Fallback for providers that send whole tool calls in one chunk."""
    for tc in chunk.tool_calls:
        tool_id = tc.get("id")
        tool_name = tc.get("name", "")
        tool_args = tc.get("args", {})

        if not tool_id or not tool_name:
            logger.warning(f"[LangChain] Skipping invalid tool call: {tc}")
            continue

        tool_calls_dict[tool_id] = {
            "id": tool_id,
            "name": tool_name,
            "args": json.dumps(tool_args) if isinstance(tool_args, dict) else tool_args,
        }


def build_tool_calls_data(tool_calls_dict: Dict[Any, Dict[str, str]]) -> List[Dict[str, Any]]:
    """Turn the accumulator into OpenAI function-calling payloads.

    Incomplete entries (no name, unparseable args) are dropped with a
    warning rather than sent upstream.
    """
    tool_calls_data = []
    for tool_index, tool_data in tool_calls_dict.items():
        tool_name = tool_data.get("name", "")
        tool_args = tool_data.get("args", "")
        tool_id = tool_data.get("id") or f"call_{tool_index}"

        if not tool_name:
            logger.warning(f"[LangChain] Skipping incomplete tool call: index={tool_index}, id={tool_id}, name={tool_name}")
            continue

        if isinstance(tool_args, str):
            # Args may be an empty string or incomplete JSON during streaming
            try:
                parsed_args = json.loads(tool_args) if tool_args.strip() else {}
            except json.JSONDecodeError as e:
                logger.warning(f"[LangChain] Failed to parse tool args JSON: {tool_args[:100]}... Error: {e}")
                continue
        else:
            parsed_args = tool_args

        tool_calls_data.append({
            "id": tool_id,
            "type": "function",
            "function": {
                "name": tool_name,
                "arguments": json.dumps(parsed_args),
            },
        })
    return tool_calls_data


def read_usage(chunk) -> Optional[Tuple[int, int, int]]:
    """`(prompt, completion, total)` token counts, when this chunk has them."""
    if not (hasattr(chunk, 'usage_metadata') and chunk.usage_metadata):
        return None
    usage = chunk.usage_metadata
    return (
        usage.get("input_tokens", 0),
        usage.get("output_tokens", 0),
        usage.get("total_tokens", 0),
    )


# --- Diagnostics -----------------------------------------------------

def log_first_chunk_structure(chunk) -> None:
    """One-off dump of a chunk's shape when reasoning is enabled."""
    logger.info("[LangChain] 🔍 Chunk structure debug:")
    logger.info(f"  - hasattr additional_kwargs: {hasattr(chunk, 'additional_kwargs')}")
    if hasattr(chunk, 'additional_kwargs'):
        logger.info(f"  - additional_kwargs keys: {chunk.additional_kwargs.keys() if chunk.additional_kwargs else 'None'}")
        logger.info(f"  - additional_kwargs content: {chunk.additional_kwargs}")
    logger.info(f"  - hasattr response_metadata: {hasattr(chunk, 'response_metadata')}")
    if hasattr(chunk, 'response_metadata'):
        logger.info(f"  - response_metadata keys: {chunk.response_metadata.keys() if chunk.response_metadata else 'None'}")
        logger.info(f"  - response_metadata content: {chunk.response_metadata}")

    if hasattr(chunk, 'raw'):
        logger.info("  - hasattr raw: True")
        logger.info(f"  - raw type: {type(chunk.raw)}")
        logger.info(f"  - raw content: {chunk.raw}")
    else:
        logger.info("  - hasattr raw: False")

    logger.info(f"  - chunk attributes: {[attr for attr in dir(chunk) if not attr.startswith('_')]}")


def log_first_image_chunk_structure(chunk) -> None:
    logger.info(f"[ImageGen] First chunk attributes: {[attr for attr in dir(chunk) if not attr.startswith('_')]}")
    if hasattr(chunk, 'additional_kwargs'):
        logger.info(f"[ImageGen] additional_kwargs: {chunk.additional_kwargs}")
    if hasattr(chunk, 'response_metadata'):
        logger.info(f"[ImageGen] response_metadata: {chunk.response_metadata}")


def log_final_chunk_structure(chunk) -> None:
    logger.info("[LangChain] 🔍 FINAL CHUNK DEBUG:")
    logger.info(f"  - chunk type: {type(chunk)}")
    logger.info(f"  - chunk dir: {[attr for attr in dir(chunk) if not attr.startswith('_')]}")
    if hasattr(chunk, 'additional_kwargs'):
        logger.info(f"  - additional_kwargs: {chunk.additional_kwargs}")
    if hasattr(chunk, 'response_metadata'):
        logger.info(f"  - response_metadata: {chunk.response_metadata}")
    if hasattr(chunk, '__dict__'):
        logger.info(f"  - __dict__: {chunk.__dict__}")
