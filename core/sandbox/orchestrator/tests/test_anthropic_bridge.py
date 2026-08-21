"""Unit tests for the Anthropic<->OpenAI bridge conversions.

Covers ``convert_request`` (Anthropic Messages -> OpenAI Chat
Completions), ``convert_response`` (OpenAI -> Anthropic), and the
tool-call mapping in both directions. Pure functions — no FastAPI
runtime, no network (the conftest stubs fastapi when it isn't
installed in the invoking venv).
"""

import json
import sys
import types


def _import_bridge():
    """Import anthropic_bridge, stubbing fastapi just for the import.

    The bridge module imports FastAPI (an orchestrator-image dep not
    present in the Django venv) but the conversion functions under test
    never touch it. The stub is removed from ``sys.modules`` right
    after the import so ``pytest.importorskip("fastapi")`` in sibling
    test modules still skips correctly.
    """
    if "anthropic_bridge" in sys.modules:
        return sys.modules["anthropic_bridge"]
    stubbed = False
    try:
        import fastapi  # noqa: F401
    except ImportError:
        stubbed = True
        fastapi_stub = types.ModuleType("fastapi")
        fastapi_stub.Request = type("Request", (), {})
        responses_stub = types.ModuleType("fastapi.responses")
        responses_stub.StreamingResponse = type("StreamingResponse", (), {})
        responses_stub.JSONResponse = type("JSONResponse", (), {})
        fastapi_stub.responses = responses_stub
        sys.modules["fastapi"] = fastapi_stub
        sys.modules["fastapi.responses"] = responses_stub
    try:
        import anthropic_bridge
    finally:
        if stubbed:
            sys.modules.pop("fastapi", None)
            sys.modules.pop("fastapi.responses", None)
    return anthropic_bridge


_bridge = _import_bridge()
_convert_content_to_openai = _bridge._convert_content_to_openai
_convert_tool_result_content = _bridge._convert_tool_result_content
_map_finish_reason = _bridge._map_finish_reason
convert_request = _bridge.convert_request
convert_response = _bridge.convert_response


class TestConvertRequest:
    def test_string_system_prompt_becomes_system_message(self):
        body = {
            "model": "openai/gpt-4o",
            "system": "You are helpful.",
            "messages": [{"role": "user", "content": "hi"}],
            "max_tokens": 100,
        }
        out = convert_request(body)
        assert out["messages"][0] == {
            "role": "system",
            "content": "You are helpful.",
        }
        assert out["messages"][1] == {"role": "user", "content": "hi"}
        assert out["model"] == "openai/gpt-4o"
        assert out["max_tokens"] == 100
        assert out["stream"] is False

    def test_block_list_system_prompt_joined(self):
        body = {
            "model": "m",
            "system": [
                {"type": "text", "text": "Line one."},
                {"type": "text", "text": "Line two."},
            ],
            "messages": [],
        }
        out = convert_request(body)
        assert out["messages"][0]["content"] == "Line one.\nLine two."

    def test_assistant_tool_use_becomes_tool_calls(self):
        body = {
            "model": "m",
            "messages": [
                {"role": "user", "content": "list files"},
                {
                    "role": "assistant",
                    "content": [
                        {"type": "text", "text": "Listing now."},
                        {
                            "type": "tool_use",
                            "id": "toolu_01",
                            "name": "Bash",
                            "input": {"command": "ls"},
                        },
                    ],
                },
            ],
        }
        out = convert_request(body)
        assistant = out["messages"][1]
        assert assistant["role"] == "assistant"
        assert assistant["content"] == "Listing now."
        (tc,) = assistant["tool_calls"]
        assert tc["id"] == "toolu_01"
        assert tc["type"] == "function"
        assert tc["function"]["name"] == "Bash"
        assert json.loads(tc["function"]["arguments"]) == {"command": "ls"}

    def test_tool_result_becomes_tool_role_message(self):
        body = {
            "model": "m",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": "toolu_01",
                            "content": "file1\nfile2",
                        },
                        {"type": "text", "text": "now summarize"},
                    ],
                }
            ],
        }
        out = convert_request(body)
        assert out["messages"][0] == {
            "role": "tool",
            "tool_call_id": "toolu_01",
            "content": "file1\nfile2",
        }
        # Remaining user text follows the tool message.
        assert out["messages"][1] == {
            "role": "user",
            "content": "now summarize",
        }

    def test_tool_result_block_list_content_flattened(self):
        assert (
            _convert_tool_result_content(
                [{"type": "text", "text": "a"}, {"type": "text", "text": "b"}]
            )
            == "a\nb"
        )

    def test_tools_converted_to_openai_functions(self):
        body = {
            "model": "m",
            "messages": [],
            "tools": [
                {
                    "name": "Read",
                    "description": "Read a file",
                    "input_schema": {
                        "type": "object",
                        "properties": {"path": {"type": "string"}},
                    },
                }
            ],
        }
        out = convert_request(body)
        (tool,) = out["tools"]
        assert tool["type"] == "function"
        assert tool["function"]["name"] == "Read"
        assert tool["function"]["description"] == "Read a file"
        assert tool["function"]["parameters"]["properties"]["path"] == {
            "type": "string"
        }

    def test_sampling_params_pass_through(self):
        body = {
            "model": "m",
            "messages": [],
            "temperature": 0.2,
            "top_p": 0.9,
            "stop_sequences": ["END"],
            "stream": True,
        }
        out = convert_request(body)
        assert out["temperature"] == 0.2
        assert out["top_p"] == 0.9
        assert out["stop"] == ["END"]
        assert out["stream"] is True

    def test_temperature_zero_is_preserved(self):
        out = convert_request(
            {"model": "m", "messages": [], "temperature": 0}
        )
        assert out["temperature"] == 0

    def test_empty_assistant_message_gets_empty_content(self):
        # OpenAI requires content or tool_calls on assistant messages.
        body = {
            "model": "m",
            "messages": [{"role": "assistant", "content": []}],
        }
        out = convert_request(body)
        assert out["messages"][0]["content"] == ""


class TestConvertContentHelper:
    def test_plain_string_passthrough(self):
        text, tool_calls = _convert_content_to_openai("hello")
        assert text == "hello"
        assert tool_calls == []

    def test_thinking_blocks_folded_into_text(self):
        text, _ = _convert_content_to_openai(
            [
                {"type": "thinking", "thinking": "hmm"},
                {"type": "text", "text": "answer"},
            ]
        )
        assert text == "hmm\nanswer"

    def test_tool_use_without_id_gets_generated_id(self):
        _, tool_calls = _convert_content_to_openai(
            [{"type": "tool_use", "name": "Read", "input": {}}]
        )
        assert tool_calls[0]["id"].startswith("call_")


class TestConvertResponse:
    def test_text_response_round_trip(self):
        openai_resp = {
            "id": "chatcmpl-123",
            "choices": [
                {
                    "message": {"role": "assistant", "content": "Hello!"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        }
        out = convert_response(openai_resp, model="openai/gpt-4o")
        assert out["type"] == "message"
        assert out["role"] == "assistant"
        assert out["model"] == "openai/gpt-4o"
        assert out["stop_reason"] == "end_turn"
        assert out["content"] == [{"type": "text", "text": "Hello!"}]
        assert out["usage"] == {"input_tokens": 10, "output_tokens": 5}

    def test_tool_calls_become_tool_use_blocks(self):
        openai_resp = {
            "choices": [
                {
                    "message": {
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call_9",
                                "type": "function",
                                "function": {
                                    "name": "Bash",
                                    "arguments": '{"command": "ls -la"}',
                                },
                            }
                        ],
                    },
                    "finish_reason": "tool_calls",
                }
            ],
            "usage": {},
        }
        out = convert_response(openai_resp, model="m")
        (block,) = out["content"]
        assert block["type"] == "tool_use"
        assert block["id"] == "call_9"
        assert block["name"] == "Bash"
        assert block["input"] == {"command": "ls -la"}
        assert out["stop_reason"] == "tool_use"

    def test_unparseable_tool_arguments_preserved_raw(self):
        openai_resp = {
            "choices": [
                {
                    "message": {
                        "tool_calls": [
                            {
                                "id": "call_1",
                                "function": {
                                    "name": "Bash",
                                    "arguments": "{broken json",
                                },
                            }
                        ]
                    },
                    "finish_reason": "tool_calls",
                }
            ],
        }
        out = convert_response(openai_resp, model="m")
        assert out["content"][0]["input"] == {"raw": "{broken json"}

    def test_empty_response_degrades_gracefully(self):
        out = convert_response({}, model="m")
        assert out["content"] == []
        assert out["stop_reason"] == "end_turn"
        assert out["usage"] == {"input_tokens": 0, "output_tokens": 0}
        assert out["id"].startswith("msg_")


class TestFinishReasonMapping:
    def test_mappings(self):
        assert _map_finish_reason("stop") == "end_turn"
        assert _map_finish_reason("length") == "max_tokens"
        assert _map_finish_reason("tool_calls") == "tool_use"
        assert _map_finish_reason("function_call") == "tool_use"
        assert _map_finish_reason("content_filter") == "end_turn"
        assert _map_finish_reason(None) == "end_turn"
        assert _map_finish_reason("something_new") == "end_turn"


class TestRoundTrip:
    def test_tool_call_survives_anthropic_openai_anthropic(self):
        """A tool_use block converted to OpenAI and back keeps its id,
        name, and input — the invariant Claude CLI relies on."""
        anthropic_msg = {
            "role": "assistant",
            "content": [
                {
                    "type": "tool_use",
                    "id": "toolu_RT",
                    "name": "Edit",
                    "input": {"file_path": "a.py", "old": "x", "new": "y"},
                }
            ],
        }
        openai_req = convert_request(
            {"model": "m", "messages": [anthropic_msg]}
        )
        tc = openai_req["messages"][0]["tool_calls"][0]

        openai_resp = {
            "choices": [
                {
                    "message": {"content": None, "tool_calls": [tc]},
                    "finish_reason": "tool_calls",
                }
            ],
        }
        back = convert_response(openai_resp, model="m")
        (block,) = back["content"]
        assert block["id"] == "toolu_RT"
        assert block["name"] == "Edit"
        assert block["input"] == {
            "file_path": "a.py",
            "old": "x",
            "new": "y",
        }
