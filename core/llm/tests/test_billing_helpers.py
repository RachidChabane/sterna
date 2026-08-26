"""Characterization tests for the pure billing-classification helper in
`llm.agent.cost_ledger`: `extract_billable_tool_costs`.

A plain function with no I/O -- no DB, no async, no mocking required.
It is the single dedup gate the agent-core turn's accounting
(`llm.agent_service.accounting.TurnAccounting`) runs every tool result
batch through, deciding which tool-reported `cost_usd` values may be
re-billed at the chat-aggregate level. Getting this wrong either
double-bills the user (coding-agent / non-OpenRouter costs re-added) or
silently drops billable dollars (image-gen or plain OpenRouter tool
costs excluded).
"""

from django.test import SimpleTestCase

from llm.agent.cost_ledger import IMAGE_GEN_TOOL_NAMES, extract_billable_tool_costs
from llm.agent_tool_handlers import CODING_AGENT_TOOL_NAMES


def _tr(tool_name, result, call_id="call_1"):
    """Build one tool_results entry in the shape the agent constructs."""
    return {
        "tool_call": {"id": call_id, "function": {"name": tool_name, "arguments": "{}"}},
        "result": result,
        "success": True,
    }


class ExtractBillableToolCostsTests(SimpleTestCase):

    def test_empty_list_yields_zero_costs(self):
        self.assertEqual(extract_billable_tool_costs([]), (0.0, 0.0))

    def test_non_dict_result_is_skipped(self):
        tool_results = [_tr("some_tool", "not-a-dict")]
        self.assertEqual(extract_billable_tool_costs(tool_results), (0.0, 0.0))

    def test_cost_usd_absent_contributes_nothing(self):
        tool_results = [_tr("some_tool", {"success": True})]
        self.assertEqual(extract_billable_tool_costs(tool_results), (0.0, 0.0))

    def test_zero_cost_not_added(self):
        tool_results = [_tr("some_tool", {"success": True, "cost_usd": 0})]
        self.assertEqual(extract_billable_tool_costs(tool_results), (0.0, 0.0))

    def test_negative_cost_not_added(self):
        """`cost > 0` guard: a negative/garbage cost must not decrement the bill."""
        tool_results = [_tr("some_tool", {"success": True, "cost_usd": -5.0})]
        self.assertEqual(extract_billable_tool_costs(tool_results), (0.0, 0.0))

    def test_plain_openrouter_tool_cost_is_billable(self):
        tool_results = [_tr("web_fetch", {"success": True, "cost_usd": 0.02})]
        tool_cost, image_gen_cost = extract_billable_tool_costs(tool_results)
        self.assertAlmostEqual(tool_cost, 0.02)
        self.assertEqual(image_gen_cost, 0.0)

    def test_missing_provider_key_defaults_to_billable(self):
        """No `provider` key at all (falsy) must NOT be treated as non-OpenRouter."""
        tool_results = [_tr("web_fetch", {"success": True, "cost_usd": 0.03})]
        tool_cost, _ = extract_billable_tool_costs(tool_results)
        self.assertAlmostEqual(tool_cost, 0.03)

    def test_explicit_openrouter_provider_is_billable(self):
        tool_results = [_tr("web_fetch", {"success": True, "cost_usd": 0.04, "provider": "openrouter"})]
        tool_cost, _ = extract_billable_tool_costs(tool_results)
        self.assertAlmostEqual(tool_cost, 0.04)

    def test_non_openrouter_provider_is_excluded(self):
        """Google AI Studio / other non-OpenRouter providers bill via their
        own _record_billing path -- must not be re-added here."""
        tool_results = [_tr("generate_video", {"success": True, "cost_usd": 1.5, "provider": "google"})]
        self.assertEqual(extract_billable_tool_costs(tool_results), (0.0, 0.0))

    def test_coding_agent_tool_names_are_always_excluded(self):
        """Coding-agent tools bill their own dedicated CODE_SESSION UsageLog
        row (see _bill_code_session in agent_tool_handlers.py) -- their
        cost_usd must never land in the chat-aggregate tool_cost, even
        though they carry a top-level cost_usd field."""
        for name in CODING_AGENT_TOOL_NAMES:
            with self.subTest(tool_name=name):
                tool_results = [_tr(name, {"success": True, "cost_usd": 3.33})]
                self.assertEqual(
                    extract_billable_tool_costs(tool_results), (0.0, 0.0),
                    f"{name} cost_usd leaked into the chat-aggregate rollup",
                )

    def test_image_gen_tools_counted_in_both_totals(self):
        """OpenRouter image-gen writes its own per-image UsageLog row --
        its cost must be returned separately (image_gen_cost) so the
        caller can subtract it from the aggregate bill, but it IS part
        of the raw tool_cost total (SSE `done.tool_cost` reports the raw
        sum, the subtraction happens at the billing call site)."""
        for name in IMAGE_GEN_TOOL_NAMES:
            with self.subTest(tool_name=name):
                tool_results = [_tr(name, {"success": True, "cost_usd": 0.02})]
                tool_cost, image_gen_cost = extract_billable_tool_costs(tool_results)
                self.assertAlmostEqual(tool_cost, 0.02)
                self.assertAlmostEqual(image_gen_cost, 0.02)

    def test_mixed_batch_sums_correctly_and_excludes_coding_agent(self):
        tool_results = [
            _tr("web_fetch", {"success": True, "cost_usd": 0.10}, call_id="1"),
            _tr("generate_image", {"success": True, "cost_usd": 0.05}, call_id="2"),
            _tr("coding_agent", {"success": True, "cost_usd": 9.99}, call_id="3"),
            _tr("plain_tool_no_cost", {"success": True}, call_id="4"),
        ]
        tool_cost, image_gen_cost = extract_billable_tool_costs(tool_results)
        self.assertAlmostEqual(tool_cost, 0.15)
        self.assertAlmostEqual(image_gen_cost, 0.05)

    def test_malformed_tool_call_shape_does_not_crash(self):
        """tool_name resolution is a chained .get() -- a tool_results entry
        missing `tool_call` or `function` must degrade to an empty name,
        not raise."""
        tool_results = [{
            "tool_call": {},  # no "function" key at all
            "result": {"success": True, "cost_usd": 0.01},
            "success": True,
        }]
        tool_cost, _ = extract_billable_tool_costs(tool_results)
        self.assertAlmostEqual(tool_cost, 0.01)

    def test_non_numeric_cost_usd_is_ignored(self):
        """A string cost_usd (bad tool implementation) must not raise or
        be silently coerced -- the `isinstance(cost, (int, float))` guard
        should skip it."""
        tool_results = [_tr("web_fetch", {"success": True, "cost_usd": "0.05"})]
        self.assertEqual(extract_billable_tool_costs(tool_results), (0.0, 0.0))
