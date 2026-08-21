"""The SSE vocabulary both streaming paths speak.

Event factory. Every event name and payload shape the frontend depends on
is declared once here, so the two streaming loops cannot drift apart on a
field name and a reader can see the whole protocol in one place.

Also holds the two small transformations applied to tool payloads on the
way out (display-name enrichment) and on the way back to the model
(result condensing).
"""

import json
import logging
from typing import Any, Dict, List

from ..brave_search_tools import condense_for_model

# Child of the configured "llm" logger (see sterna/logging.py APP_LOGGERS).
logger = logging.getLogger(__name__)

# --- Event names -----------------------------------------------------

EVENT_CONTENT = "content"
EVENT_REASONING = "reasoning"
EVENT_IMAGE = "image"
EVENT_DONE = "done"
EVENT_ERROR = "error"
EVENT_HEARTBEAT = "heartbeat"
EVENT_USAGE_UPDATE = "usage_update"
EVENT_GENERATION_ID = "generation_id"
EVENT_FILE_TOOL_EXECUTING = "file_tool_executing"
EVENT_FILE_TOOL_EXECUTED = "file_tool_executed"
EVENT_WEB_SOURCES = "web_sources"
EVENT_PREVIEW_STARTED = "preview_started"
EVENT_CONTEXT_TRIMMED = "context_trimmed"
EVENT_CONTEXT_COMPACTED = "context_compacted"

FINISH_REASON_CANCELLED = "cancelled"
FINISH_REASON_STOP = "stop"
FINISH_REASON_TOOL_CALLS = "tool_calls"
FINISH_REASON_INVALID_TOOLS = "invalid_tools"

ERROR_CODE_NO_TOOL_SUPPORT = "NO_TOOL_SUPPORT"
ERROR_CODE_CONTEXT_TOO_LARGE = "CONTEXT_TOO_LARGE"
ERROR_CODE_QUOTA_EXCEEDED = "QUOTA_EXCEEDED"
ERROR_CODE_FEATURE_NOT_AVAILABLE = "FEATURE_NOT_AVAILABLE"
ERROR_REASONING = "reasoning_error"

CANCELLED_BY_USER_MESSAGE = "Cancelled by user"
REASONING_ERROR_DETAIL = (
    "The model attempted an invalid operation. Please try again with different settings."
)

# Placeholder tool call shown while the model is still streaming its call.
LOADING_TOOL_CALL_ID = "loading"

TOOL_NAME_START_PREVIEW = "start_preview"


# --- Terminal / control events ---------------------------------------

def terminal_event(model: str, finish_reason: str) -> Dict[str, Any]:
    """A `done` event that carries no usage (cancellation, invalid tools)."""
    return {
        "event": EVENT_DONE,
        "data": {
            "model": model,
            "finish_reason": finish_reason,
            "usage": {},
            "cost": 0,
        },
    }


def cancelled_event(model: str) -> Dict[str, Any]:
    """The `done` event emitted when the user stopped the stream."""
    return terminal_event(model, FINISH_REASON_CANCELLED)


def cancelled_placeholder_executed_event() -> Dict[str, Any]:
    """Close out a `file_tool_executing` placeholder that never ran.

    Sent when cancellation lands after the spinner was shown but before
    any real tool call was resolved.
    """
    return {
        "event": EVENT_FILE_TOOL_EXECUTED,
        "data": {
            "tool_calls": [{
                "function": {"name": "...", "arguments": "{}"},
                "id": LOADING_TOOL_CALL_ID,
                "type": "function",
            }],
            "results": [{
                "tool_call": {},
                "result": {"success": False, "error": CANCELLED_BY_USER_MESSAGE},
                "success": False,
            }],
        },
    }


def loading_tool_call_event() -> Dict[str, Any]:
    """Show the tool spinner on the first streamed tool-call fragment."""
    return {
        "event": EVENT_FILE_TOOL_EXECUTING,
        "data": {
            "tool_calls": [{
                "function": {"name": "...", "arguments": "{}"},
                "id": LOADING_TOOL_CALL_ID,
                "type": "function",
            }],
        },
    }


def cancelled_tool_result(tool_call: Dict[str, Any]) -> Dict[str, Any]:
    """A tool-results entry standing in for a tool that never ran."""
    return {
        "tool_call": tool_call,
        "result": {"success": False, "error": CANCELLED_BY_USER_MESSAGE},
        "success": False,
    }


def usage_update_event(
    *,
    prompt_tokens: int,
    completion_tokens: int,
    total_tokens: int,
    cost: float,
    prompt_cost: float,
    completion_cost: float,
    generation_id,
    generation_ids,
) -> Dict[str, Any]:
    """Partial usage, so the frontend has figures if the user stops."""
    return {
        "event": EVENT_USAGE_UPDATE,
        "data": {
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
            },
            "cost": cost,
            "prompt_cost": prompt_cost,
            "completion_cost": completion_cost,
            "generation_id": generation_id,
            "generation_ids": generation_ids,
        },
    }


def no_tool_support_error_event(model: str) -> Dict[str, Any]:
    return {
        "event": EVENT_ERROR,
        "data": {
            "error": "Model does not support tools",
            "detail": f"The model '{model}' does not support function calling/tools. Please select a different model or disable tool-dependent features.",
            "code": ERROR_CODE_NO_TOOL_SUPPORT,
        },
    }


def api_error_event(detail: str) -> Dict[str, Any]:
    return {"event": EVENT_ERROR, "data": {"error": "API Error", "detail": detail}}


def context_too_large_event(detail: str) -> Dict[str, Any]:
    return {
        "event": EVENT_ERROR,
        "data": {
            "error": "Context Too Large",
            "detail": detail,
            "code": ERROR_CODE_CONTEXT_TOO_LARGE,
        },
    }


def reasoning_error_event() -> Dict[str, Any]:
    return {
        "event": EVENT_ERROR,
        "data": {"error": ERROR_REASONING, "detail": REASONING_ERROR_DETAIL},
    }


def quota_error_event(exc, *, feature_not_available: bool) -> Dict[str, Any]:
    return {
        "event": EVENT_ERROR,
        "data": {
            **exc.to_response_dict(),
            "code": (
                ERROR_CODE_FEATURE_NOT_AVAILABLE
                if feature_not_available
                else ERROR_CODE_QUOTA_EXCEEDED
            ),
        },
    }


# --- Tool payload shaping --------------------------------------------

def add_display_names(
    tool_calls: List[Dict[str, Any]],
    display_names: Dict[str, str],
    server_icons: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Add display_name and server icon info to each tool call for user-friendly UI display.
    """
    enriched = []
    for tc in tool_calls:
        tc_copy = tc.copy()
        tool_name = tc.get("function", {}).get("name", "")
        # Look up display name, fall back to the raw tool name if not found
        tc_copy["display_name"] = display_names.get(tool_name, tool_name)
        server_icon = server_icons.get(tool_name)
        if server_icon:
            tc_copy["server_icon_url"] = server_icon.get("url")
            tc_copy["server_icon_invert"] = server_icon.get("invert", False)
        enriched.append(tc_copy)
    return enriched


def post_tool_events(tool_results: list) -> list:
    """Generate additional SSE events based on tool results.

    Centralizes detection for start_preview and any future tools
    that need custom SSE events after execution.
    Returns a list of event dicts to yield.
    """
    events = []
    for tr in tool_results:
        tc = tr.get("tool_call", {})
        tool_name = tc.get("function", {}).get("name", "")
        result_data = tr.get("result", {})
        if isinstance(result_data, str):
            try:
                result_data = json.loads(result_data)
            except (json.JSONDecodeError, TypeError):
                result_data = {}
        if tool_name == TOOL_NAME_START_PREVIEW and isinstance(result_data, dict) and result_data.get("success"):
            events.append({
                "event": EVENT_PREVIEW_STARTED,
                "data": {
                    "port": result_data.get("port"),
                    "command": result_data.get("command"),
                    "pid": result_data.get("pid"),
                },
            })
    return events


def format_tool_result_for_llm(tool_name: str, result: Any) -> str:
    """
    Format tool results for the LLM.
    Condenses Brave search results to reduce token usage.
    (Frontend gets full data via SSE, model gets condensed version)
    """
    if tool_name.startswith('brave_') and isinstance(result, dict):
        return json.dumps(condense_for_model(result), ensure_ascii=False)

    if isinstance(result, dict):
        return json.dumps(result, ensure_ascii=False)
    return str(result)
