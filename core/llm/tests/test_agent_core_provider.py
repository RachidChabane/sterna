"""Unit tests for the provider port's pure building blocks.

Covers the SSE line/chunk parsing in `llm.agent_core.sse_parsing`, the
tool-call delta accumulator, and the HTTP-status-to-exception mapping
in `llm.agent_core.provider_errors` — none of it needs a transport.
"""

import unittest

from llm.agent_core.events import ToolCall, ToolCallFunction
from llm.agent_core.provider import (
    ProviderContentDeltaChunk,
    ProviderDoneChunk,
    ProviderGenerationIdChunk,
    ProviderImageChunk,
    ProviderReasoningDeltaChunk,
    ProviderToolCallDeltaChunk,
    ProviderUsageChunk,
)
from llm.agent_core.provider_errors import (
    ProviderAuthError,
    ProviderInvalidRequestError,
    ProviderOverloadedError,
    ProviderQuotaExceededError,
    ProviderRateLimitError,
    ProviderResponseError,
    map_status_to_error,
)
from llm.agent_core.sse_parsing import (
    DONE_MARKER,
    extract_stream_error,
    iter_sse_payloads,
    parse_stream_chunk,
    sse_payload,
)
from llm.agent_core.tool_call_accumulator import ToolCallAccumulator


class SsePayloadParsingTests(unittest.TestCase):
    def test_data_line_yields_its_payload(self):
        self.assertEqual(sse_payload('data: {"id": "gen-1"}'), '{"id": "gen-1"}')

    def test_data_line_without_a_space_is_also_accepted(self):
        self.assertEqual(sse_payload('data:{"id": "gen-1"}'), '{"id": "gen-1"}')

    def test_blank_line_carries_no_payload(self):
        self.assertIsNone(sse_payload(""))

    def test_comment_line_carries_no_payload(self):
        self.assertIsNone(sse_payload(": OPENROUTER PROCESSING"))

    def test_iter_sse_payloads_skips_blanks_and_comments(self):
        lines = [
            ": keep-alive",
            'data: {"a": 1}',
            "",
            'data: {"b": 2}',
            f"data: {DONE_MARKER}",
        ]
        self.assertEqual(
            list(iter_sse_payloads(lines)),
            ['{"a": 1}', '{"b": 2}', DONE_MARKER],
        )


class StreamErrorExtractionTests(unittest.TestCase):
    def test_error_object_is_extracted(self):
        raw = {"error": {"code": 429, "message": "Rate limit exceeded"}}
        self.assertEqual(extract_stream_error(raw), {"code": 429, "message": "Rate limit exceeded"})

    def test_missing_error_key_yields_none(self):
        self.assertIsNone(extract_stream_error({"choices": []}))

    def test_non_dict_error_value_yields_none(self):
        self.assertIsNone(extract_stream_error({"error": "boom"}))


class ParseStreamChunkTests(unittest.TestCase):
    def test_generation_id_is_first_when_present(self):
        raw = {"id": "gen-1", "choices": [{"delta": {"content": "hi"}}]}
        chunks = parse_stream_chunk(raw)
        self.assertIsInstance(chunks[0], ProviderGenerationIdChunk)
        self.assertEqual(chunks[0].generation_id, "gen-1")
        self.assertEqual(chunks[1], ProviderContentDeltaChunk(content="hi"))

    def test_chunk_without_id_yields_no_generation_id_chunk(self):
        raw = {"choices": [{"delta": {"content": "hi"}}]}
        chunks = parse_stream_chunk(raw)
        self.assertNotIsInstance(chunks[0], ProviderGenerationIdChunk)

    def test_empty_content_delta_yields_no_content_chunk(self):
        raw = {"choices": [{"delta": {"content": ""}}]}
        self.assertEqual(parse_stream_chunk(raw), [])

    def test_tool_call_delta_is_parsed(self):
        raw = {
            "choices": [
                {
                    "delta": {
                        "tool_calls": [
                            {"index": 0, "id": "call-1", "function": {"name": "search", "arguments": ""}}
                        ]
                    }
                }
            ]
        }
        chunks = parse_stream_chunk(raw)
        self.assertEqual(
            chunks,
            [ProviderToolCallDeltaChunk(index=0, id="call-1", name="search", arguments_delta="")],
        )

    def test_tool_call_argument_fragment_carries_only_the_delta(self):
        raw = {"choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"arguments": '{"q":'}}]}}]}
        chunks = parse_stream_chunk(raw)
        self.assertEqual(
            chunks,
            [ProviderToolCallDeltaChunk(index=0, id=None, name=None, arguments_delta='{"q":')],
        )

    def test_reasoning_details_text_is_parsed(self):
        raw = {
            "choices": [
                {"delta": {"reasoning_details": [{"type": "reasoning.text", "text": "thinking..."}]}}
            ]
        }
        self.assertEqual(parse_stream_chunk(raw), [ProviderReasoningDeltaChunk(content="thinking...")])

    def test_reasoning_details_summary_is_parsed(self):
        raw = {
            "choices": [
                {"delta": {"reasoning_details": [{"type": "reasoning.summary", "summary": "short"}]}}
            ]
        }
        self.assertEqual(parse_stream_chunk(raw), [ProviderReasoningDeltaChunk(content="short")])

    def test_legacy_reasoning_field_is_parsed_when_no_details_array(self):
        raw = {"choices": [{"delta": {"reasoning": "hmm"}}]}
        self.assertEqual(parse_stream_chunk(raw), [ProviderReasoningDeltaChunk(content="hmm")])

    def test_image_dict_shape_is_parsed(self):
        raw = {
            "choices": [
                {"delta": {"images": [{"type": "image_url", "image_url": {"url": "data:image/png;..."}}]}}
            ]
        }
        self.assertEqual(parse_stream_chunk(raw), [ProviderImageChunk(image="data:image/png;...")])

    def test_bare_string_image_is_parsed(self):
        raw = {"choices": [{"delta": {"images": ["data:image/png;..."]}}]}
        self.assertEqual(parse_stream_chunk(raw), [ProviderImageChunk(image="data:image/png;...")])

    def test_finish_reason_yields_a_done_chunk(self):
        raw = {"choices": [{"delta": {}, "finish_reason": "tool_calls"}]}
        self.assertEqual(parse_stream_chunk(raw), [ProviderDoneChunk(finish_reason="tool_calls")])

    def test_null_finish_reason_yields_no_done_chunk(self):
        raw = {"choices": [{"delta": {"content": "hi"}, "finish_reason": None}]}
        chunks = parse_stream_chunk(raw)
        self.assertNotIn(ProviderDoneChunk(finish_reason=None), chunks)

    def test_usage_is_parsed_with_cost_details(self):
        raw = {
            "choices": [],
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "total_tokens": 15,
                "cost": 0.0004,
                "cost_details": {"upstream_inference_cost": 0.0003},
            },
        }
        chunks = parse_stream_chunk(raw)
        self.assertEqual(len(chunks), 1)
        usage_chunk = chunks[0]
        self.assertIsInstance(usage_chunk, ProviderUsageChunk)
        self.assertEqual(usage_chunk.usage.total_tokens, 15)
        self.assertEqual(usage_chunk.cost, 0.0004)
        self.assertEqual(usage_chunk.upstream_inference_cost, 0.0003)

    def test_usage_precedes_the_done_chunk_when_both_arrive_in_the_final_chunk(self):
        raw = {
            "choices": [{"delta": {}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }
        chunks = parse_stream_chunk(raw)
        self.assertIsInstance(chunks[0], ProviderUsageChunk)
        self.assertEqual(chunks[1], ProviderDoneChunk(finish_reason="stop"))


class ToolCallAccumulatorTests(unittest.TestCase):
    def test_single_call_accumulates_across_fragments(self):
        accumulator = ToolCallAccumulator()
        accumulator.absorb(ProviderToolCallDeltaChunk(index=0, id="call-1", name="search", arguments_delta=""))
        accumulator.absorb(ProviderToolCallDeltaChunk(index=0, arguments_delta='{"q":'))
        accumulator.absorb(ProviderToolCallDeltaChunk(index=0, arguments_delta='"sterna"}'))

        self.assertEqual(
            accumulator.tool_calls(),
            [ToolCall(id="call-1", function=ToolCallFunction(name="search", arguments='{"q":"sterna"}'))],
        )

    def test_placeholder_empty_object_is_replaced_not_concatenated(self):
        accumulator = ToolCallAccumulator()
        accumulator.absorb(ProviderToolCallDeltaChunk(index=0, id="call-1", name="search", arguments_delta="{}"))
        accumulator.absorb(ProviderToolCallDeltaChunk(index=0, arguments_delta='{"q": "sterna"}'))

        self.assertEqual(
            accumulator.tool_calls()[0].function.arguments,
            '{"q": "sterna"}',
        )

    def test_placeholder_empty_object_arriving_later_is_ignored(self):
        accumulator = ToolCallAccumulator()
        accumulator.absorb(ProviderToolCallDeltaChunk(index=0, id="call-1", name="search", arguments_delta='{"q": 1}'))
        accumulator.absorb(ProviderToolCallDeltaChunk(index=0, arguments_delta="{}"))

        self.assertEqual(accumulator.tool_calls()[0].function.arguments, '{"q": 1}')

    def test_multiple_indices_preserve_first_seen_order(self):
        accumulator = ToolCallAccumulator()
        accumulator.absorb(ProviderToolCallDeltaChunk(index=1, id="call-b", name="two", arguments_delta="{}"))
        accumulator.absorb(ProviderToolCallDeltaChunk(index=0, id="call-a", name="one", arguments_delta="{}"))

        calls = accumulator.tool_calls()
        self.assertEqual([call.id for call in calls], ["call-b", "call-a"])

    def test_empty_accumulator_is_falsy(self):
        self.assertFalse(ToolCallAccumulator())

    def test_absorbing_a_delta_makes_it_truthy(self):
        accumulator = ToolCallAccumulator()
        accumulator.absorb(ProviderToolCallDeltaChunk(index=0, id="call-1"))
        self.assertTrue(accumulator)


class MapStatusToErrorTests(unittest.TestCase):
    def test_429_maps_to_rate_limit_with_retry_after(self):
        error = map_status_to_error(429, "Rate limit exceeded", retry_after=12.0)
        self.assertIsInstance(error, ProviderRateLimitError)
        self.assertEqual(error.retry_after, 12.0)
        self.assertEqual(error.status_code, 429)

    def test_401_and_403_map_to_auth_error(self):
        self.assertIsInstance(map_status_to_error(401, "Missing Authentication header"), ProviderAuthError)
        self.assertIsInstance(map_status_to_error(403, "Forbidden"), ProviderAuthError)

    def test_402_maps_to_quota_exceeded(self):
        self.assertIsInstance(map_status_to_error(402, "Insufficient credits"), ProviderQuotaExceededError)

    def test_400_maps_to_invalid_request(self):
        self.assertIsInstance(map_status_to_error(400, "Bad request"), ProviderInvalidRequestError)

    def test_5xx_and_5xx_like_codes_map_to_overloaded(self):
        for status_code in (500, 502, 503, 524, 529):
            with self.subTest(status_code=status_code):
                self.assertIsInstance(map_status_to_error(status_code, "unavailable"), ProviderOverloadedError)

    def test_unrecognized_status_maps_to_generic_response_error(self):
        error = map_status_to_error(418, "I'm a teapot")
        self.assertIsInstance(error, ProviderResponseError)
        self.assertEqual(error.status_code, 418)


if __name__ == "__main__":
    unittest.main()
