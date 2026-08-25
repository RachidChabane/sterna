"""Tests for OptimizedPromptBuilder's capability-notice parity.

Covers the direct-completion path (OpenRouterClient.complete/stream via
`_inject_system_prompt`) alongside the LangChain agent path, since both
draw from the same STATIC_CORE_PROMPTS toggleable_capabilities section.
"""

from django.test import TestCase

from ..prompts_v2.optimized_builder import OptimizedPromptBuilder

CAPABILITIES_MARKER = "Available Capabilities"


class TestToggleableCapabilitiesParity(TestCase):
    """The toggleable-capabilities notice must reach every completion path."""

    def setUp(self):
        self.builder = OptimizedPromptBuilder()

    def test_direct_completion_prompt_includes_capabilities_section(self):
        """The non-agent OpenRouterClient completion path must advertise
        toggleable capabilities, matching the agent path."""
        prompt = self.builder.build_direct_completion_prompt()

        self.assertIn(CAPABILITIES_MARKER, prompt)

    def test_direct_completion_prompt_includes_capabilities_with_features_enabled(self):
        """The section stays present regardless of which direct-path
        feature flags are also active."""
        prompt = self.builder.build_direct_completion_prompt(
            enable_reasoning=True,
            enable_file_tools=True,
            enable_image_generation=True,
        )

        self.assertIn(CAPABILITIES_MARKER, prompt)

    def test_agent_path_still_includes_capabilities_section(self):
        """The LangChain agent path (build_cacheable_prompt, via
        STATIC_CORE_PROMPTS) must continue to include the same section."""
        prompt, _metadata = self.builder.build_cacheable_prompt()

        self.assertIn(CAPABILITIES_MARKER, prompt)
