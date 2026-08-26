"""Guard: every tool a V2 system prompt tells the model it has must be one
the turn's `ToolRegistry` actually offers.

`prompts_v2.modular_prompts.STATIC_CORE_PROMPTS` and `CONDITIONAL_PROMPTS`
name specific tool ids by contract -- "use `search_available_tools`",
"you have `generate_image`" -- and `registry_factory.build_tool_set`
decides, independently, which `ToolDefinition`s a turn's registry holds.
Nothing ties the two together: a tool named in a prompt section with no
matching registry entry tells the model it can call something the loop
will reject as unknown the moment it tries.

`SECTION_TOOL_IDS` is a hand-maintained map from prompt section id to the
tool ids that section names -- a regex over free-form prose would
false-positive on illustrative text like `tool_naming`'s "'read_file', not
'read_file'" examples, so the ids to look for are curated by hand instead
of parsed out. Two things keep that map honest: every id it claims a
section names must actually appear in that section's own content
(`SectionToolIdsDriftTests`), and every `STATIC_CORE_PROMPTS` /
`CONDITIONAL_PROMPTS` entry must have an entry in the map, so a newly
added section with no coverage fails loudly rather than passing by
omission (`SectionToolIdsCoverageTests`).

`KNOWN_UNOFFERED` is every tool id this guard already knows is named in a
reachable prompt section without a matching registry entry, each keyed to
the exact condition under which the gap is real. It is not a general
escape hatch: `UnofferedExemptionsAreStillRealTests` asserts each one is
still actually missing from the registry under the condition that exempts
it, so fixing the gap (or a mismatch, if the underlying gate changes)
breaks that test and forces the exemption back out.
"""

from __future__ import annotations

import asyncio
import dataclasses
import unittest
from itertools import product
from typing import Dict, FrozenSet

from llm.agent.feature_flags import AgentFeatureFlags
from llm.agent.prompt_assembly import build_agent_system_prompt
from llm.agent_service.registry_factory import build_tool_set
from llm.prompts_v2.modular_prompts import CONDITIONAL_PROMPTS, STATIC_CORE_PROMPTS

GUARD_USER_ID = "guard-user"
GUARD_CONVERSATION_ID = "guard-conversation"

# Prompt section id -> tool ids that section names by contract. Every
# `STATIC_CORE_PROMPTS` section id and every `CONDITIONAL_PROMPTS` key
# must appear here, even where the value is the empty set.
SECTION_TOOL_IDS: Dict[str, FrozenSet[str]] = {
    # STATIC_CORE_PROMPTS -- always included, every V2 turn.
    "intellectual_perspective": frozenset(),
    "language": frozenset(),
    "toggleable_capabilities": frozenset(),
    "tool_action_format": frozenset(),
    "tool_naming": frozenset(),
    "tool_discovery": frozenset({"search_available_tools", "get_tool_details"}),
    "response_quality": frozenset(),
    # CONDITIONAL_PROMPTS -- included when the matching feature is on.
    "file_tools": frozenset(
        {
            "read_file",
            "write_file",
            "edit_file",
            "list_files",
            "execute_code",
            "execute_programming_task",
            "start_preview",
            "stop_preview",
        }
    ),
    "reasoning": frozenset(),
    "web_search": frozenset(),
    "brave_search": frozenset({"search_available_tools", "brave_web_search"}),
    "google_maps": frozenset(
        {
            "geocode_address",
            "get_directions",
            "search_nearby_places",
            "get_air_quality",
            "get_street_view",
        }
    ),
    "mcp_tools": frozenset({"search_available_tools"}),
    "voice_mode": frozenset(),
    "image_generation": frozenset({"generate_image", "edit_image"}),
    "video_generation": frozenset({"generate_video", "animate_image", "animate_character"}),
    "coding_agent": frozenset({"coding_agent", "list_coding_agents", "update_coding_agent"}),
    "sparks": frozenset({"create_spark", "update_spark"}),
    "spark_auto_fix": frozenset(),
    "spark_ignite": frozenset(),
    "knowledge_base": frozenset({"query_knowledge_base"}),
}

# Tool id -> predicate(flags) that is True exactly when the gap is real:
# the id is named by a section reachable under `flags`, but has no
# `agent_core.tools` entry, so `build_tool_set`'s registry cannot offer
# it under that condition.
KNOWN_UNOFFERED = {
    # Mandated by `tool_discovery` (STATIC_CORE, every V2 turn) but bound
    # only when the request has a tool-backed feature (see
    # `registry_factory.build_tool_set`'s module docstring) -- a
    # knowledge_base-only or reasoning-only turn's prompt still mandates
    # both with neither bound.
    "search_available_tools": lambda flags: not flags.has_tool_features,
    "get_tool_details": lambda flags: not flags.has_tool_features,
    # Bound as callables by `AgentToolRegistry.load_initial_tools` when
    # the matching flag is on, but no `agent_core.tools` module wraps
    # either id, so `_definitions_for` drops it from the registry.
    "create_spark": lambda flags: flags.sparks,
    "update_spark": lambda flags: flags.sparks,
    "start_preview": lambda flags: flags.file_tools,
    "stop_preview": lambda flags: flags.file_tools,
    # An `agent_core.tools` module exists for this id, but
    # `AgentToolRegistry.load_initial_tools` never binds it as a callable
    # for `file_tools` (`llm.agent_tool_handlers.FILE_TOOLS` -- the V2
    # tool group -- omits it; only V1's separate
    # `sandbox.orchestrator.file_tools.FILE_TOOLS` contract carries it),
    # so `_definitions_for` has no bound name to match the module against.
    "execute_programming_task": lambda flags: flags.file_tools,
}

FLAG_FIELDS = [field.name for field in dataclasses.fields(AgentFeatureFlags)]


def _prompt_for(flags: AgentFeatureFlags) -> str:
    return build_agent_system_prompt(
        custom_prompt=None,
        flags=flags,
        discovery_context=None,
        model_name=None,
        user_first_name=None,
        user_last_name=None,
        user_email=None,
        spark_fix_request=None,
        spark_ignite_request=None,
        forced_tool_name=None,
        media_tool_params=None,
    )


def _registry_ids(flags: AgentFeatureFlags) -> frozenset:
    tool_set = asyncio.run(
        build_tool_set(
            flags,
            user_id=GUARD_USER_ID,
            conversation_id=GUARD_CONVERSATION_ID,
            mcp_tools=None,
        )
    )
    return frozenset(definition.id for definition in tool_set.registry.all())


def _all_flag_combinations():
    for values in product([False, True], repeat=len(FLAG_FIELDS)):
        yield AgentFeatureFlags(**dict(zip(FLAG_FIELDS, values)))


class SectionToolIdsDriftTests(unittest.TestCase):
    """`SECTION_TOOL_IDS` claims are checked against the sections themselves."""

    def test_every_claimed_id_appears_in_its_section_s_content(self):
        by_id = {section.id: section for section in STATIC_CORE_PROMPTS}
        by_id.update(CONDITIONAL_PROMPTS)

        missing = []
        for section_id, tool_ids in SECTION_TOOL_IDS.items():
            section = by_id.get(section_id)
            if section is None:
                continue  # covered by SectionToolIdsCoverageTests instead
            for tool_id in tool_ids:
                if tool_id not in section.content:
                    missing.append((section_id, tool_id))
        self.assertEqual(
            missing,
            [],
            f"SECTION_TOOL_IDS claims a tool id not present in its section's content: {missing}",
        )


class SectionToolIdsCoverageTests(unittest.TestCase):
    """Every real prompt section has a `SECTION_TOOL_IDS` entry, even if empty."""

    def test_every_static_core_section_is_covered(self):
        missing = {section.id for section in STATIC_CORE_PROMPTS} - set(SECTION_TOOL_IDS)
        self.assertEqual(missing, set(), f"STATIC_CORE section(s) with no SECTION_TOOL_IDS entry: {sorted(missing)}")

    def test_every_conditional_prompt_key_is_covered(self):
        missing = set(CONDITIONAL_PROMPTS) - set(SECTION_TOOL_IDS)
        self.assertEqual(missing, set(), f"CONDITIONAL_PROMPTS key(s) with no SECTION_TOOL_IDS entry: {sorted(missing)}")


class PromptMandatedToolsAreOfferedTests(unittest.TestCase):
    """The guard proper: every flag combination's prompt vs. its registry."""

    def test_every_prompt_mandated_tool_is_offered_or_a_known_gap(self):
        failures = []
        for flags in _all_flag_combinations():
            prompt = _prompt_for(flags)
            enabled = flags.prompt_feature_names()
            expected = set(SECTION_TOOL_IDS["tool_discovery"])  # STATIC_CORE, always present
            for feature, ids in SECTION_TOOL_IDS.items():
                if feature in enabled:
                    expected |= ids
            # Only tool ids the prompt text actually names count -- a
            # section present in SECTION_TOOL_IDS but whose CONDITIONAL_PROMPTS
            # key can never land in `enabled` (dead entries such as
            # "coding_agent") contributes nothing here regardless.
            expected = {tool_id for tool_id in expected if tool_id in prompt}

            registry_ids = _registry_ids(flags)
            for tool_id in expected - registry_ids:
                exemption = KNOWN_UNOFFERED.get(tool_id)
                if exemption is not None and exemption(flags):
                    continue
                failures.append((flags, tool_id))

        self.assertEqual(
            failures,
            [],
            "prompt-mandated tool(s) missing from the registry, with no "
            f"recorded exemption (flags, tool_id): {failures}",
        )


class UnofferedExemptionsAreStillRealTests(unittest.TestCase):
    """Each `KNOWN_UNOFFERED` entry is still an actual gap, not stale cover.

    If a future change adds the missing `agent_core.tools` module, or
    changes the gate so the tool is offered under the exempting
    condition, the matching assertion here fails -- forcing the
    exemption to be deleted rather than silently continuing to mask a
    fixed gap.
    """

    def test_search_available_tools_is_missing_without_a_tool_feature(self):
        registry_ids = _registry_ids(AgentFeatureFlags(knowledge_base=True))
        self.assertNotIn("search_available_tools", registry_ids)
        self.assertNotIn("get_tool_details", registry_ids)

    def test_spark_tools_are_missing_from_the_registry(self):
        registry_ids = _registry_ids(AgentFeatureFlags(sparks=True))
        self.assertNotIn("create_spark", registry_ids)
        self.assertNotIn("update_spark", registry_ids)

    def test_preview_tools_are_missing_from_the_registry(self):
        registry_ids = _registry_ids(AgentFeatureFlags(file_tools=True))
        self.assertNotIn("start_preview", registry_ids)
        self.assertNotIn("stop_preview", registry_ids)

    def test_execute_programming_task_is_missing_from_the_registry(self):
        registry_ids = _registry_ids(AgentFeatureFlags(file_tools=True))
        self.assertNotIn("execute_programming_task", registry_ids)


if __name__ == "__main__":
    unittest.main()
