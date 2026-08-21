#!/usr/bin/env python3
"""
MCP stdio relay for ask_user tool.

Minimal MCP server (JSON-RPC 2.0 over stdin/stdout) that relays questions
from the coding agent CLI to the orchestrator, which forwards them to the
user via SSE. Blocks until the user responds or timeout is reached.

Injected into the sandbox container at runtime. Uses only stdlib.
"""

import argparse
import json
import sys
import urllib.request
import urllib.error

TOOL_DESCRIPTION = (
    "Ask the user a question and wait for their response. Use when you need "
    "clarification or a decision that would meaningfully change your approach. "
    "Do not ask for confirmation on routine operations. If you provide options, "
    "the user's answer will be one of the option labels exactly."
)

ORCHESTRATOR_URL = "http://sterna-orchestrator:8003"
HTTP_TIMEOUT = 310  # Slightly above server's 300s timeout


def send_response(response: dict) -> None:
    """Write a JSON-RPC response to stdout."""
    line = json.dumps(response)
    sys.stdout.write(line + "\n")
    sys.stdout.flush()


def handle_initialize(msg: dict) -> dict:
    return {
        "jsonrpc": "2.0",
        "id": msg["id"],
        "result": {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "ask-user", "version": "1.0.0"},
        },
    }


def handle_tools_list(msg: dict) -> dict:
    return {
        "jsonrpc": "2.0",
        "id": msg["id"],
        "result": {
            "tools": [
                {
                    "name": "ask_user",
                    "description": TOOL_DESCRIPTION,
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "question": {
                                "type": "string",
                                "description": "The question to ask the user.",
                            },
                            "options": {
                                "type": "array",
                                "description": "Optional list of choices for the user.",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "label": {"type": "string"},
                                        "description": {"type": "string"},
                                    },
                                    "required": ["label", "description"],
                                },
                            },
                        },
                        "required": ["question"],
                    },
                }
            ]
        },
    }


def handle_tools_call(msg: dict, user_id: str, chat_id: str, token: str) -> dict:
    args = msg.get("params", {}).get("arguments", {})
    question = args.get("question", "")
    options = args.get("options")

    payload = json.dumps({
        "user_id": user_id,
        "chat_id": chat_id,
        "job_token": token,
        "question": question,
        "options": options,
    }).encode("utf-8")

    try:
        req = urllib.request.Request(
            f"{ORCHESTRATOR_URL}/mcp/ask-user",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
            result = json.loads(resp.read().decode("utf-8"))

        answer = result.get("answer", "")
        if answer == "__CANCELLED__":
            return {
                "jsonrpc": "2.0",
                "id": msg["id"],
                "result": {
                    "content": [{"type": "text", "text": "The user cancelled the operation."}],
                    "isError": True,
                },
            }

        return {
            "jsonrpc": "2.0",
            "id": msg["id"],
            "result": {
                "content": [{"type": "text", "text": answer}],
            },
        }

    except Exception as exc:
        return {
            "jsonrpc": "2.0",
            "id": msg["id"],
            "result": {
                "content": [{"type": "text", "text": f"Error reaching user: {exc}"}],
                "isError": True,
            },
        }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--user-id", required=True)
    parser.add_argument("--chat-id", required=True)
    parser.add_argument("--token", required=True)
    args = parser.parse_args()

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue

        method = msg.get("method", "")

        if method == "initialize":
            send_response(handle_initialize(msg))
        elif method == "notifications/initialized":
            pass  # No response needed for notifications
        elif method == "tools/list":
            send_response(handle_tools_list(msg))
        elif method == "tools/call":
            send_response(handle_tools_call(msg, args.user_id, args.chat_id, args.token))
        elif msg.get("id") is not None:
            # Unknown method with id — return error
            send_response({
                "jsonrpc": "2.0",
                "id": msg["id"],
                "error": {"code": -32601, "message": f"Method not found: {method}"},
            })


if __name__ == "__main__":
    main()
