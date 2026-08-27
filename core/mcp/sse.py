"""Server-Sent Events parsing for the MCP Streamable HTTP transport.

A Streamable HTTP POST may answer with a `text/event-stream` body
instead of a plain JSON object; this module extracts the JSON-RPC
message carried by its first `message` event.
"""

import json
from typing import List

from .exceptions import MCPConnectionError
from .protocol import MCPResponse


async def parse_sse_response(response) -> MCPResponse:
    """Parse a Server-Sent Events response from MCP Streamable HTTP.

    SSE format:
        event: message
        data: {"jsonrpc":"2.0","result":...,"id":1}

    Args:
        response: httpx streaming response

    Returns:
        MCPResponse from the first message event
    """
    event_type = None
    data_lines: List[str] = []

    async for line in response.aiter_lines():
        line = line.strip()

        if not line:
            # Empty line marks end of event
            if event_type == "message" and data_lines:
                data = "\n".join(data_lines)
                try:
                    parsed = json.loads(data)
                    return MCPResponse.from_dict(parsed)
                except json.JSONDecodeError as e:
                    raise MCPConnectionError(f"Failed to parse SSE data: {e}")
            # Reset for next event
            event_type = None
            data_lines = []
            continue

        if line.startswith("event:"):
            event_type = line[6:].strip()
        elif line.startswith("data:"):
            data_lines.append(line[5:].strip())

    # Handle case where stream ends without empty line
    if event_type == "message" and data_lines:
        data = "\n".join(data_lines)
        try:
            parsed = json.loads(data)
            return MCPResponse.from_dict(parsed)
        except json.JSONDecodeError as e:
            raise MCPConnectionError(f"Failed to parse SSE data: {e}")

    raise MCPConnectionError("No valid response received from SSE stream")
