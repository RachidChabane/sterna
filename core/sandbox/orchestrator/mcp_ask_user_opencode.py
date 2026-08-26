#!/usr/bin/env python3
"""MCP stdio server exposing ask_user to an opencode run.

opencode reaches a local MCP server by spawning it and speaking
JSON-RPC 2.0 over stdin/stdout, and exposes its tools to the model as
``{server}_{tool}`` — so the ``ask_user`` tool of the ``ask-user``
server is offered as ``ask-user_ask_user``.

A call relays the question to the orchestrator, which raises it to the
user over SSE, and blocks on the reply. The job identity travels in the
environment rather than the command line so it does not show in the
sandbox's process list.

Injected into the sandbox container at runtime. Uses only stdlib.
"""

import json
import os
import sys
import urllib.request

TOOL_NAME = "ask_user"
TOOL_DESCRIPTION = (
    "Ask the user a question and wait for their response. Use when you need "
    "clarification or a decision that would meaningfully change your approach. "
    "Do not ask for confirmation on routine operations. If you provide options, "
    "the user's answer will be one of the option labels exactly."
)

ORCHESTRATOR_URL = os.environ.get(
    "STERNA_ORCHESTRATOR_URL", "http://sterna-orchestrator:8003"
)
ASK_USER_PATH = "/mcp/ask-user"

#: Slightly above the orchestrator's own 300s wait for the user.
HTTP_TIMEOUT = 310

CANCELLED_ANSWER = "__CANCELLED__"
CANCELLED_MESSAGE = "The user cancelled the operation."

PROTOCOL_VERSION = "2024-11-05"
METHOD_NOT_FOUND = -32601

TOOL_SCHEMA = {
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
}


class JobIdentity:
    """The job this relay speaks for, as the runner configured it."""

    def __init__(self) -> None:
        self.user_id = os.environ.get("STERNA_USER_ID", "")
        self.chat_id = os.environ.get("STERNA_CHAT_ID", "")
        self.job_token = os.environ.get("STERNA_JOB_TOKEN", "")


def send(response: dict) -> None:
    sys.stdout.write(json.dumps(response) + "\n")
    sys.stdout.flush()


def result(message_id, payload: dict) -> dict:
    return {"jsonrpc": "2.0", "id": message_id, "result": payload}


def text_result(message_id, text: str, is_error: bool = False) -> dict:
    payload = {"content": [{"type": "text", "text": text}]}
    if is_error:
        payload["isError"] = True
    return result(message_id, payload)


def handle_initialize(message: dict) -> dict:
    return result(
        message["id"],
        {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "ask-user", "version": "1.0.0"},
        },
    )


def handle_tools_list(message: dict) -> dict:
    return result(
        message["id"],
        {
            "tools": [
                {
                    "name": TOOL_NAME,
                    "description": TOOL_DESCRIPTION,
                    "inputSchema": TOOL_SCHEMA,
                }
            ]
        },
    )


def relay_question(question: str, options, identity: JobIdentity) -> str:
    """Put the question to the orchestrator and wait for the answer."""
    payload = json.dumps(
        {
            "user_id": identity.user_id,
            "chat_id": identity.chat_id,
            "job_token": identity.job_token,
            "question": question,
            "options": options,
        }
    ).encode("utf-8")

    request = urllib.request.Request(
        ORCHESTRATOR_URL + ASK_USER_PATH,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT) as response:
        answer = json.loads(response.read().decode("utf-8"))
    return answer.get("answer", "")


def handle_tools_call(message: dict, identity: JobIdentity) -> dict:
    arguments = (message.get("params") or {}).get("arguments") or {}
    try:
        answer = relay_question(
            arguments.get("question", ""), arguments.get("options"), identity
        )
    except Exception as exc:  # noqa: BLE001 - any failure must reach the model
        return text_result(message["id"], f"Error reaching user: {exc}", is_error=True)

    if answer == CANCELLED_ANSWER:
        return text_result(message["id"], CANCELLED_MESSAGE, is_error=True)
    return text_result(message["id"], answer)


def main() -> None:
    identity = JobIdentity()

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            continue

        method = message.get("method", "")
        if method == "initialize":
            send(handle_initialize(message))
        elif method == "tools/list":
            send(handle_tools_list(message))
        elif method == "tools/call":
            send(handle_tools_call(message, identity))
        elif message.get("id") is not None:
            send(
                {
                    "jsonrpc": "2.0",
                    "id": message["id"],
                    "error": {
                        "code": METHOD_NOT_FOUND,
                        "message": f"Method not found: {method}",
                    },
                }
            )


if __name__ == "__main__":
    main()
