"""Unit tests for claude_output_parser — billing-critical cost extraction.

The parser feeds ``total_cost_usd`` into the two-layer billing chain
(claude_output_parser -> coding_agent_runner -> coding_agent_service ->
agent_tool_handlers -> accumulated_tool_cost), so cost extraction and
resilience to malformed stream-json output are load-bearing.

Pure unit tests: no docker, no network.
"""

import json

from claude_output_parser import ClaudeOutputParser, parse_claude_output


def _result_event(**overrides):
    event = {
        "type": "result",
        "subtype": "success",
        "result": "All done.",
        "total_cost_usd": 0.0523,
        "usage": {"input_tokens": 1200, "output_tokens": 345},
    }
    event.update(overrides)
    return json.dumps(event)


class TestCostExtraction:
    def test_total_cost_usd_propagates_to_result(self):
        output = "\n".join(
            [
                json.dumps({"type": "system", "subtype": "init"}),
                json.dumps(
                    {
                        "type": "assistant",
                        "message": {
                            "content": [{"type": "text", "text": "working"}]
                        },
                    }
                ),
                _result_event(total_cost_usd=0.1234),
            ]
        )
        result = parse_claude_output(output)
        assert result.total_cost_usd == 0.1234
        assert result.success is True
        assert result.summary == "All done."

    def test_missing_cost_defaults_to_zero(self):
        # Event without the key -> 0.0, never None.
        event = json.loads(_result_event())
        del event["total_cost_usd"]
        result = parse_claude_output(json.dumps(event))
        assert result.total_cost_usd == 0.0

    def test_token_usage_extracted(self):
        result = parse_claude_output(_result_event())
        assert result.total_tokens == 1200 + 345

    def test_model_usage_breakdown_takes_max(self):
        event = json.loads(_result_event())
        event["modelUsage"] = {
            "some/model": {"inputTokens": 5000, "outputTokens": 1000},
        }
        result = parse_claude_output(json.dumps(event))
        assert result.total_tokens == 6000

    def test_cost_zero_when_no_result_event(self):
        output = json.dumps(
            {
                "type": "assistant",
                "message": {"content": [{"type": "text", "text": "hi"}]},
            }
        )
        result = parse_claude_output(output)
        assert result.total_cost_usd == 0.0


class TestMalformedInput:
    def test_malformed_jsonl_lines_are_skipped(self):
        output = "\n".join(
            [
                "{not valid json",
                '{"type": "assistant" INVALID',
                _result_event(),
                "",
                "   ",
                "also-not-json",
            ]
        )
        result = parse_claude_output(output)
        # Malformed lines are dropped; the valid result still parses.
        assert result.success is True
        assert result.total_cost_usd == 0.0523

    def test_zero_output_is_failure(self):
        """The '0 output despite exit code 0' regression: an empty
        stream must not be reported as success."""
        result = parse_claude_output("")
        assert result.success is False
        assert result.total_cost_usd == 0.0
        assert result.total_tokens == 0
        assert result.steps == []

    def test_only_malformed_lines_is_failure(self):
        result = parse_claude_output("garbage\nmore garbage\n")
        assert result.success is False

    def test_unknown_event_types_are_ignored(self):
        output = "\n".join(
            [
                json.dumps({"type": "totally_new_event", "x": 1}),
                _result_event(),
            ]
        )
        result = parse_claude_output(output)
        assert result.success is True

    def test_error_event_marks_failure(self):
        output = "\n".join(
            [
                json.dumps({"type": "error", "message": "boom"}),
                _result_event(),
            ]
        )
        result = parse_claude_output(output)
        assert result.success is False
        assert result.error == "boom"


class TestFileTracking:
    def _tool_use(self, name, **input_data):
        return json.dumps(
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {"type": "tool_use", "name": name, "input": input_data}
                    ]
                },
            }
        )

    def test_write_of_unread_file_is_created(self):
        output = "\n".join(
            [
                self._tool_use("Write", file_path="src/new.py"),
                _result_event(),
            ]
        )
        result = parse_claude_output(output)
        assert result.files_created == ["src/new.py"]
        assert result.files_modified == []

    def test_write_after_read_is_modified(self):
        output = "\n".join(
            [
                self._tool_use("Read", file_path="src/app.py"),
                self._tool_use("Write", file_path="src/app.py"),
                _result_event(),
            ]
        )
        result = parse_claude_output(output)
        assert result.files_modified == ["src/app.py"]
        assert result.files_created == []

    def test_edit_is_always_modified(self):
        output = "\n".join(
            [
                self._tool_use("Edit", file_path="./src/x.py"),
                _result_event(),
            ]
        )
        result = parse_claude_output(output)
        # leading ./ normalized away
        assert result.files_modified == ["src/x.py"]


class TestSummaryFallbacks:
    def test_last_assistant_message_used_without_result(self):
        output = json.dumps(
            {
                "type": "assistant",
                "message": {
                    "content": [{"type": "text", "text": "final words"}]
                },
            }
        )
        result = parse_claude_output(output)
        assert result.summary == "final words"

    def test_sub_agent_text_does_not_override_main_summary(self):
        output = "\n".join(
            [
                json.dumps(
                    {
                        "type": "assistant",
                        "parent_tool_use_id": "toolu_123",
                        "message": {
                            "content": [
                                {"type": "text", "text": "sub-agent noise"}
                            ]
                        },
                    }
                ),
                json.dumps(
                    {
                        "type": "assistant",
                        "message": {
                            "content": [{"type": "text", "text": "main text"}]
                        },
                    }
                ),
            ]
        )
        result = parse_claude_output(output)
        assert result.summary == "main text"


class TestIncrementalParsing:
    def test_parse_line_returns_none_for_blank(self):
        parser = ClaudeOutputParser()
        assert parser.parse_line("") is None
        assert parser.parse_line("   ") is None

    def test_parse_line_accumulates_state(self):
        parser = ClaudeOutputParser()
        step = parser.parse_line(_result_event())
        assert step is not None
        assert step.type == "result"
        assert parser.total_cost_usd == 0.0523
