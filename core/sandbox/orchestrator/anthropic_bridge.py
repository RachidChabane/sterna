"""
Anthropic-to-OpenAI Bridge

Translates between the Anthropic Messages API format and the OpenAI Chat
Completions API format. This enables Claude Code CLI (which speaks Anthropic
format) to work with non-Anthropic models through OpenRouter's
/api/v1/chat/completions endpoint.

Architecture:
  Claude CLI  ─(Anthropic format)─►  Bridge  ─(OpenAI format)─►  OpenRouter
  Claude CLI  ◄─(Anthropic format)──  Bridge  ◄─(OpenAI format)──  OpenRouter
"""

import json
import os
import uuid
import logging
from typing import Any, AsyncIterator, Optional

import httpx
from fastapi import Request
from fastapi.responses import StreamingResponse, JSONResponse

logger = logging.getLogger(__name__)

# OpenRouter chat completions endpoint
OPENROUTER_CHAT_URL = "https://openrouter.ai/api/v1/chat/completions"

# Public site URL sent as the OpenRouter attribution header. Neutral default
# so a fresh deployment doesn't advertise someone else's domain; override
# with the real public URL in production (mirrors Django's
# OPENROUTER_SITE_URL setting — this service runs outside Django).
OPENROUTER_SITE_URL = os.environ.get("OPENROUTER_SITE_URL", "https://example.com")

# Timeout for upstream requests (10 minutes for long coding tasks)
UPSTREAM_TIMEOUT = 600.0


# ---------------------------------------------------------------------------
# Request conversion: Anthropic Messages → OpenAI Chat Completions
# ---------------------------------------------------------------------------

def _convert_content_to_openai(content) -> tuple[Optional[str], list]:
    """Convert Anthropic content (string or blocks) to OpenAI format.

    Returns (text_content, tool_calls).
    """
    if isinstance(content, str):
        return content, []

    if not isinstance(content, list):
        return str(content) if content else None, []

    text_parts = []
    tool_calls = []

    for block in content:
        block_type = block.get("type")

        if block_type == "text":
            text_parts.append(block.get("text", ""))

        elif block_type == "tool_use":
            tool_calls.append({
                "id": block.get("id", f"call_{uuid.uuid4().hex[:12]}"),
                "type": "function",
                "function": {
                    "name": block.get("name", ""),
                    "arguments": json.dumps(block.get("input", {})),
                },
            })

        elif block_type == "tool_result":
            # tool_result blocks are handled at the message level
            pass

        elif block_type == "image":
            # Pass image as a content part (OpenAI vision format)
            source = block.get("source", {})
            if source.get("type") == "base64":
                text_parts.append(f"[Image: {source.get('media_type', 'image')}]")

        elif block_type == "thinking":
            # Extended thinking - include as text
            text_parts.append(block.get("thinking", ""))

    text = "\n".join(text_parts) if text_parts else None
    return text, tool_calls


def _convert_tool_result_content(content) -> str:
    """Convert tool_result content to a string for OpenAI format."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                if block.get("type") == "text":
                    parts.append(block.get("text", ""))
                elif block.get("type") == "image":
                    parts.append("[Image]")
                else:
                    parts.append(json.dumps(block))
        return "\n".join(parts)
    return str(content) if content else ""


def convert_request(anthropic_body: dict) -> dict:
    """Convert an Anthropic Messages API request to OpenAI Chat Completions format."""
    openai_messages = []

    # System prompt → system message
    system = anthropic_body.get("system")
    if system:
        if isinstance(system, str):
            openai_messages.append({"role": "system", "content": system})
        elif isinstance(system, list):
            # Anthropic system can be a list of content blocks
            parts = []
            for block in system:
                if isinstance(block, str):
                    parts.append(block)
                elif isinstance(block, dict) and block.get("type") == "text":
                    parts.append(block.get("text", ""))
            openai_messages.append({"role": "system", "content": "\n".join(parts)})

    # Convert messages
    for msg in anthropic_body.get("messages", []):
        role = msg.get("role")
        content = msg.get("content")

        if role == "user":
            # Check for tool_result blocks in user messages
            if isinstance(content, list):
                tool_results = [b for b in content if isinstance(b, dict) and b.get("type") == "tool_result"]
                other_blocks = [b for b in content if not (isinstance(b, dict) and b.get("type") == "tool_result")]

                # Add tool result messages first
                for tr in tool_results:
                    openai_messages.append({
                        "role": "tool",
                        "tool_call_id": tr.get("tool_use_id", ""),
                        "content": _convert_tool_result_content(tr.get("content", "")),
                    })

                # Add remaining user content if any
                if other_blocks:
                    text, _ = _convert_content_to_openai(other_blocks)
                    if text:
                        openai_messages.append({"role": "user", "content": text})
            else:
                text, _ = _convert_content_to_openai(content)
                openai_messages.append({"role": "user", "content": text or ""})

        elif role == "assistant":
            text, tool_calls = _convert_content_to_openai(content)
            msg_dict: dict[str, Any] = {"role": "assistant"}
            if text:
                msg_dict["content"] = text
            if tool_calls:
                msg_dict["tool_calls"] = tool_calls
            # OpenAI requires content or tool_calls
            if not text and not tool_calls:
                msg_dict["content"] = ""
            openai_messages.append(msg_dict)

    # Convert tools
    openai_tools = None
    if anthropic_body.get("tools"):
        openai_tools = []
        for tool in anthropic_body["tools"]:
            openai_tools.append({
                "type": "function",
                "function": {
                    "name": tool.get("name", ""),
                    "description": tool.get("description", ""),
                    "parameters": tool.get("input_schema", {"type": "object"}),
                },
            })

    # Build OpenAI request
    openai_body: dict[str, Any] = {
        "model": anthropic_body.get("model", ""),
        "messages": openai_messages,
        "stream": anthropic_body.get("stream", False),
    }

    if anthropic_body.get("max_tokens"):
        openai_body["max_tokens"] = anthropic_body["max_tokens"]

    if anthropic_body.get("temperature") is not None:
        openai_body["temperature"] = anthropic_body["temperature"]

    if anthropic_body.get("top_p") is not None:
        openai_body["top_p"] = anthropic_body["top_p"]

    if anthropic_body.get("stop_sequences"):
        openai_body["stop"] = anthropic_body["stop_sequences"]

    if openai_tools:
        openai_body["tools"] = openai_tools

    return openai_body


# ---------------------------------------------------------------------------
# Non-streaming response conversion: OpenAI → Anthropic
# ---------------------------------------------------------------------------

def _map_finish_reason(reason: Optional[str]) -> str:
    """Map OpenAI finish_reason to Anthropic stop_reason."""
    mapping = {
        "stop": "end_turn",
        "length": "max_tokens",
        "tool_calls": "tool_use",
        "content_filter": "end_turn",
        "function_call": "tool_use",
    }
    return mapping.get(reason or "", "end_turn")


def convert_response(openai_resp: dict, model: str) -> dict:
    """Convert an OpenAI Chat Completions response to Anthropic Messages format."""
    choice = openai_resp.get("choices", [{}])[0]
    message = choice.get("message", {})

    content_blocks = []

    # Text content
    if message.get("content"):
        content_blocks.append({
            "type": "text",
            "text": message["content"],
        })

    # Tool calls → tool_use blocks
    for tc in message.get("tool_calls", []):
        fn = tc.get("function", {})
        try:
            input_data = json.loads(fn.get("arguments", "{}"))
        except json.JSONDecodeError:
            input_data = {"raw": fn.get("arguments", "")}

        content_blocks.append({
            "type": "tool_use",
            "id": tc.get("id", f"toolu_{uuid.uuid4().hex[:12]}"),
            "name": fn.get("name", ""),
            "input": input_data,
        })

    usage = openai_resp.get("usage", {})

    return {
        "id": openai_resp.get("id", f"msg_{uuid.uuid4().hex[:12]}"),
        "type": "message",
        "role": "assistant",
        "content": content_blocks,
        "model": model,
        "stop_reason": _map_finish_reason(choice.get("finish_reason")),
        "stop_sequence": None,
        "usage": {
            "input_tokens": usage.get("prompt_tokens", 0),
            "output_tokens": usage.get("completion_tokens", 0),
        },
    }


# ---------------------------------------------------------------------------
# Streaming response conversion: OpenAI SSE → Anthropic SSE
# ---------------------------------------------------------------------------

def _sse_event(event_type: str, data: dict) -> str:
    """Format an Anthropic SSE event."""
    return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"


async def convert_streaming_response(
    openai_stream: AsyncIterator[bytes],
    model: str,
    input_tokens: int = 0,
) -> AsyncIterator[str]:
    """Convert an OpenAI streaming response to Anthropic SSE format.

    Yields Anthropic-format SSE events.
    """
    message_id = f"msg_{uuid.uuid4().hex[:12]}"

    # Emit message_start
    yield _sse_event("message_start", {
        "type": "message_start",
        "message": {
            "id": message_id,
            "type": "message",
            "role": "assistant",
            "content": [],
            "model": model,
            "stop_reason": None,
            "stop_sequence": None,
            "usage": {
                "input_tokens": input_tokens,
                "output_tokens": 0,
            },
        },
    })

    # Track state
    current_block_index = -1
    text_block_open = False
    tool_blocks: dict[int, dict] = {}  # tool_call_index → {id, name, args_buffer}
    output_tokens = 0
    stop_reason = "end_turn"
    line_buffer = ""

    async for chunk_bytes in openai_stream:
        chunk_text = chunk_bytes.decode("utf-8", errors="replace")
        line_buffer += chunk_text

        while "\n" in line_buffer:
            line, line_buffer = line_buffer.split("\n", 1)
            line = line.strip()

            if not line.startswith("data: "):
                continue

            data_str = line[6:]
            if data_str == "[DONE]":
                # Close any open text block
                if text_block_open:
                    yield _sse_event("content_block_stop", {
                        "type": "content_block_stop",
                        "index": current_block_index,
                    })
                    text_block_open = False

                # Close any open tool blocks
                for tc_idx in sorted(tool_blocks.keys()):
                    tc = tool_blocks[tc_idx]
                    if tc.get("open"):
                        yield _sse_event("content_block_stop", {
                            "type": "content_block_stop",
                            "index": tc["block_index"],
                        })

                # Emit message_delta and message_stop
                yield _sse_event("message_delta", {
                    "type": "message_delta",
                    "delta": {
                        "stop_reason": stop_reason,
                        "stop_sequence": None,
                    },
                    "usage": {
                        "output_tokens": output_tokens,
                    },
                })
                yield _sse_event("message_stop", {"type": "message_stop"})
                return

            try:
                data = json.loads(data_str)
            except json.JSONDecodeError:
                continue

            # Extract usage if present
            if data.get("usage"):
                output_tokens = data["usage"].get("completion_tokens", output_tokens)

            choices = data.get("choices", [])
            if not choices:
                continue

            delta = choices[0].get("delta", {})
            finish_reason = choices[0].get("finish_reason")

            if finish_reason:
                stop_reason = _map_finish_reason(finish_reason)

            # Handle text content delta
            # Skip empty content deltas (OpenAI sometimes sends content=""
            # after tool_calls, which would create spurious empty text blocks)
            if delta.get("content"):
                text_content = delta["content"]

                if not text_block_open:
                    current_block_index += 1
                    yield _sse_event("content_block_start", {
                        "type": "content_block_start",
                        "index": current_block_index,
                        "content_block": {"type": "text", "text": ""},
                    })
                    text_block_open = True

                yield _sse_event("content_block_delta", {
                    "type": "content_block_delta",
                    "index": current_block_index,
                    "delta": {
                        "type": "text_delta",
                        "text": text_content,
                    },
                })

            # Handle tool_calls delta
            if delta.get("tool_calls"):
                # Close text block if open
                if text_block_open:
                    yield _sse_event("content_block_stop", {
                        "type": "content_block_stop",
                        "index": current_block_index,
                    })
                    text_block_open = False

                for tc_delta in delta["tool_calls"]:
                    tc_idx = tc_delta.get("index", 0)

                    if tc_idx not in tool_blocks:
                        # New tool call - start block
                        current_block_index += 1
                        tc_id = tc_delta.get("id", f"toolu_{uuid.uuid4().hex[:12]}")
                        tc_name = tc_delta.get("function", {}).get("name", "")

                        tool_blocks[tc_idx] = {
                            "id": tc_id,
                            "name": tc_name,
                            "args_buffer": "",
                            "block_index": current_block_index,
                            "open": True,
                        }

                        yield _sse_event("content_block_start", {
                            "type": "content_block_start",
                            "index": current_block_index,
                            "content_block": {
                                "type": "tool_use",
                                "id": tc_id,
                                "name": tc_name,
                                "input": {},
                            },
                        })

                    # Accumulate arguments
                    fn_delta = tc_delta.get("function", {})
                    args_chunk = fn_delta.get("arguments", "")

                    # Update name if provided in later chunks
                    if fn_delta.get("name") and not tool_blocks[tc_idx]["name"]:
                        tool_blocks[tc_idx]["name"] = fn_delta["name"]

                    if args_chunk:
                        tool_blocks[tc_idx]["args_buffer"] += args_chunk
                        yield _sse_event("content_block_delta", {
                            "type": "content_block_delta",
                            "index": tool_blocks[tc_idx]["block_index"],
                            "delta": {
                                "type": "input_json_delta",
                                "partial_json": args_chunk,
                            },
                        })

    # If stream ends without [DONE], clean up
    if text_block_open:
        yield _sse_event("content_block_stop", {
            "type": "content_block_stop",
            "index": current_block_index,
        })
    for tc_idx in sorted(tool_blocks.keys()):
        tc = tool_blocks[tc_idx]
        if tc.get("open"):
            yield _sse_event("content_block_stop", {
                "type": "content_block_stop",
                "index": tc["block_index"],
            })

    yield _sse_event("message_delta", {
        "type": "message_delta",
        "delta": {"stop_reason": stop_reason, "stop_sequence": None},
        "usage": {"output_tokens": output_tokens},
    })
    yield _sse_event("message_stop", {"type": "message_stop"})


# ---------------------------------------------------------------------------
# Main handler
# ---------------------------------------------------------------------------

async def handle_messages_request(request: Request) -> StreamingResponse | JSONResponse:
    """Handle a POST /v1/messages request by bridging to OpenAI format.

    The API key is read from the Authorization header (Bearer token)
    or the x-api-key header.
    """
    body = await request.json()
    model = body.get("model", "")
    is_streaming = body.get("stream", False)

    # Extract API key from headers
    auth_header = request.headers.get("authorization", "")
    api_key = request.headers.get("x-api-key", "")
    if auth_header.startswith("Bearer "):
        api_key = auth_header[7:]

    if not api_key:
        return JSONResponse(
            status_code=401,
            content={"error": {"type": "authentication_error", "message": "Missing API key"}},
        )

    logger.info(f"[Bridge] Converting request for model={model}, stream={is_streaming}")

    # Convert request
    openai_body = convert_request(body)

    # Forward to OpenRouter
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": OPENROUTER_SITE_URL,
        "X-Title": "Sterna Coding Agent",
    }

    if is_streaming:
        return await _handle_streaming(openai_body, headers, model)
    else:
        return await _handle_non_streaming(openai_body, headers, model)


async def _handle_non_streaming(
    openai_body: dict,
    headers: dict,
    model: str,
) -> JSONResponse:
    """Handle a non-streaming request."""
    async with httpx.AsyncClient(timeout=UPSTREAM_TIMEOUT) as client:
        try:
            resp = await client.post(OPENROUTER_CHAT_URL, json=openai_body, headers=headers)
        except httpx.TimeoutException:
            return JSONResponse(
                status_code=504,
                content={"error": {"type": "timeout", "message": "Upstream request timed out"}},
            )

    if resp.status_code != 200:
        logger.error(f"[Bridge] Upstream error {resp.status_code}: {resp.text[:500]}")
        return JSONResponse(status_code=resp.status_code, content=resp.json())

    openai_resp = resp.json()
    anthropic_resp = convert_response(openai_resp, model)
    return JSONResponse(content=anthropic_resp)


async def _handle_streaming(
    openai_body: dict,
    headers: dict,
    model: str,
) -> StreamingResponse:
    """Handle a streaming request."""
    openai_body["stream"] = True

    client = httpx.AsyncClient(timeout=UPSTREAM_TIMEOUT)

    try:
        resp = await client.send(
            client.build_request("POST", OPENROUTER_CHAT_URL, json=openai_body, headers=headers),
            stream=True,
        )
    except httpx.TimeoutException:
        await client.aclose()
        return JSONResponse(
            status_code=504,
            content={"error": {"type": "timeout", "message": "Upstream request timed out"}},
        )

    if resp.status_code != 200:
        body = await resp.aread()
        await resp.aclose()
        await client.aclose()
        logger.error(f"[Bridge] Upstream error {resp.status_code}: {body[:500]}")
        try:
            error_json = json.loads(body)
        except Exception:
            error_json = {"error": {"message": body.decode("utf-8", errors="replace")}}
        return JSONResponse(status_code=resp.status_code, content=error_json)

    async def stream_generator():
        try:
            async for event_str in convert_streaming_response(
                resp.aiter_bytes(), model
            ):
                yield event_str
        finally:
            await resp.aclose()
            await client.aclose()

    return StreamingResponse(
        stream_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
