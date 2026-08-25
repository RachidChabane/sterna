"""The ten golden scenarios, replayed against the agent loop.

Each scenario feeds the loop the same generations the golden fixture
fed its legacy streaming path -- the same text, the same tool calls,
the same token counts, the same mid-stream failure -- and declares the
divergences that stand between the loop's stream and the committed
transcript.
"""

from __future__ import annotations

import dataclasses
import json
from typing import Any, Callable, List, Sequence, Tuple

from llm.agent_core.graph import AgentTurnConfig, CostBreakdown, GraphDependencies
from llm.agent_core.provider_errors import ProviderTransportError
from llm.agent_core.registry import ToolApproval, ToolDefinition, ToolRegistry
from llm.tests.agent_core_doubles import ScriptedProvider, execution_context
from llm.tests.golden.harness import (
    CATALOG_TOOL_CALL_ID,
    CATALOG_TOOL_NAME,
    COMPLETION_PRICE_PER_1K_TOKENS,
    FILE_TOOL_CALL_ID,
    FILE_TOOL_NAME,
    FOLLOW_UP_GENERATION_ID,
    GENERATION_ID,
    MODEL_ID,
    PROMPT_PRICE_PER_1K_TOKENS,
    PROVIDER_ERROR_MESSAGE,
)

from . import divergences as d
from .doubles import (
    PriceTableCostAccountant,
    ReportedCostSplit,
    SearchResultCitations,
    StoredApprovals,
    content_chunk,
    done_chunk,
    generation_id_chunk,
    tool_call_chunk,
    tool_definition,
    usage_chunk,
)

# --- Fixture constants ----------------------------------------------------

PROMPT = "Summarize the notes."
TEMPERATURE = 0.2
MAX_TOKENS = 256

FILE_TOOL_DISPLAY_NAME = "Read File"
FILE_TOOL_DESCRIPTION = "Read a file from the workspace."
FILE_TOOL_ARGUMENTS = json.dumps({"path": "/workspace/notes.md"})
FILE_TOOL_RESULT = {"success": True, "content": "# Notes\nfirst line\n"}
FILE_TOOL_SCHEMA = {
    "type": "object",
    "properties": {"path": {"type": "string"}},
    "required": ["path"],
}

CATALOG_TOOL_DISPLAY_NAME = "Web Search"
CATALOG_TOOL_DESCRIPTION = "Search the web for current information."
CATALOG_TOOL_ARGUMENTS = json.dumps({"query": "sterna streaming"})
CATALOG_TOOL_RESULT = {
    "success": True,
    "results": [{"url": "https://example.invalid/sterna", "title": "Sterna streaming"}],
}
CATALOG_TOOL_SCHEMA = {
    "type": "object",
    "properties": {"query": {"type": "string"}},
    "required": ["query"],
}
SEARCH_SERVER_NAME = "Fixture Search Server"

DISPLAY_NAMES = {
    FILE_TOOL_NAME: FILE_TOOL_DISPLAY_NAME,
    CATALOG_TOOL_NAME: CATALOG_TOOL_DISPLAY_NAME,
}

V2_ERROR_LABEL = "Stream error"

FIRST_CALL_INDEX = 0
SECOND_CALL_INDEX = 1

STOP = "stop"
TOOL_CALLS = "tool_calls"

# The split the V1 provider reports alongside its total, one per generation.
V1_FIRST_GENERATION_COST = CostBreakdown(total=0.00032, prompt=0.00012, completion=0.0002)
V1_FOLLOW_UP_GENERATION_COST = CostBreakdown(
    total=0.00025, prompt=0.00012, completion=0.0002
)


@dataclasses.dataclass(frozen=True, slots=True)
class ParityScenario:
    """One golden transcript, the run that reproduces it, and its divergences."""

    name: str
    build_dependencies: Callable[[], GraphDependencies]
    divergences: Tuple[d.Divergence, ...]


# --- Tool catalogs ---------------------------------------------------------


def _file_tool() -> ToolDefinition:
    return tool_definition(
        FILE_TOOL_NAME,
        display_name=FILE_TOOL_DISPLAY_NAME,
        description=FILE_TOOL_DESCRIPTION,
        result=FILE_TOOL_RESULT,
        approval=ToolApproval.AUTO,
        parameters=FILE_TOOL_SCHEMA,
    )


def _catalog_tool(approval: ToolApproval) -> ToolDefinition:
    return tool_definition(
        CATALOG_TOOL_NAME,
        display_name=CATALOG_TOOL_DISPLAY_NAME,
        description=CATALOG_TOOL_DESCRIPTION,
        result=CATALOG_TOOL_RESULT,
        approval=approval,
        server_name=SEARCH_SERVER_NAME,
        parameters=CATALOG_TOOL_SCHEMA,
    )


def _gated_catalog_registry() -> ToolRegistry:
    """V1 runs its file tools inline and gates every catalog tool."""

    return ToolRegistry([_file_tool(), _catalog_tool(ToolApproval.REQUIRED)])


def _open_catalog_registry() -> ToolRegistry:
    """V2 binds every tool it was given and runs them without a gate."""

    return ToolRegistry([_file_tool(), _catalog_tool(ToolApproval.AUTO)])


# --- Dependency assembly ---------------------------------------------------


def _dependencies(
    script: Sequence[Any], *, registry: ToolRegistry, cost_accountant: Any
) -> GraphDependencies:
    return GraphDependencies(
        provider=ScriptedProvider(script),
        registry=registry,
        config=AgentTurnConfig(
            model=MODEL_ID,
            temperature=TEMPERATURE,
            max_tokens=MAX_TOKENS,
            heartbeat_interval_seconds=None,
        ),
        tool_context=execution_context(),
        approvals=StoredApprovals(),
        cost_accountant=cost_accountant,
        tool_result_events=SearchResultCitations(),
    )


def _v1_dependencies(script: Sequence[Any], *costs: CostBreakdown) -> GraphDependencies:
    return _dependencies(
        script,
        registry=_gated_catalog_registry(),
        cost_accountant=ReportedCostSplit(costs),
    )


def _v2_dependencies(script: Sequence[Any]) -> GraphDependencies:
    return _dependencies(
        script,
        registry=_open_catalog_registry(),
        cost_accountant=PriceTableCostAccountant(
            prompt_price_per_1k=float(PROMPT_PRICE_PER_1K_TOKENS),
            completion_price_per_1k=float(COMPLETION_PRICE_PER_1K_TOKENS),
        ),
    )


def _file_call_chunk(index: int = FIRST_CALL_INDEX):
    return tool_call_chunk(index, FILE_TOOL_CALL_ID, FILE_TOOL_NAME, FILE_TOOL_ARGUMENTS)


def _catalog_call_chunk(index: int = FIRST_CALL_INDEX):
    return tool_call_chunk(
        index, CATALOG_TOOL_CALL_ID, CATALOG_TOOL_NAME, CATALOG_TOOL_ARGUMENTS
    )


def _provider_failure() -> ProviderTransportError:
    return ProviderTransportError(PROVIDER_ERROR_MESSAGE)


# --- V1 scenarios ------------------------------------------------------------


def _v1_plain_text() -> GraphDependencies:
    return _v1_dependencies(
        [
            [
                generation_id_chunk(GENERATION_ID),
                content_chunk("The notes "),
                content_chunk("list two "),
                content_chunk("open items."),
                usage_chunk(120, 40, cost=V1_FIRST_GENERATION_COST.total),
                done_chunk(STOP),
            ]
        ],
        V1_FIRST_GENERATION_COST,
    )


def _v1_file_tool_round_trip() -> GraphDependencies:
    return _v1_dependencies(
        [
            [
                generation_id_chunk(GENERATION_ID),
                content_chunk("Reading the file."),
                _file_call_chunk(),
                usage_chunk(120, 40, cost=V1_FIRST_GENERATION_COST.total),
                done_chunk(TOOL_CALLS),
            ],
            [
                generation_id_chunk(FOLLOW_UP_GENERATION_ID),
                content_chunk("The notes "),
                content_chunk("open with a heading."),
                usage_chunk(200, 25, cost=V1_FOLLOW_UP_GENERATION_COST.total),
                done_chunk(STOP),
            ],
        ],
        V1_FIRST_GENERATION_COST,
        V1_FOLLOW_UP_GENERATION_COST,
    )


def _v1_catalog_tool_approval_gate() -> GraphDependencies:
    return _v1_dependencies(
        [
            [
                generation_id_chunk(GENERATION_ID),
                content_chunk("Searching the web."),
                _catalog_call_chunk(),
                usage_chunk(120, 40, cost=V1_FIRST_GENERATION_COST.total),
                done_chunk(TOOL_CALLS),
            ]
        ],
        V1_FIRST_GENERATION_COST,
    )


def _v1_file_and_catalog_tools() -> GraphDependencies:
    return _v1_dependencies(
        [
            [
                generation_id_chunk(GENERATION_ID),
                content_chunk("Reading the file and searching the web."),
                _file_call_chunk(FIRST_CALL_INDEX),
                _catalog_call_chunk(SECOND_CALL_INDEX),
                usage_chunk(120, 40, cost=V1_FIRST_GENERATION_COST.total),
                done_chunk(TOOL_CALLS),
            ]
        ],
        V1_FIRST_GENERATION_COST,
    )


def _v1_provider_error() -> GraphDependencies:
    return _v1_dependencies(
        [
            [
                generation_id_chunk(GENERATION_ID),
                content_chunk("The notes "),
                _provider_failure(),
            ]
        ],
        V1_FIRST_GENERATION_COST,
    )


# --- V2 scenarios ------------------------------------------------------------


def _v2_plain_text() -> GraphDependencies:
    return _v2_dependencies(
        [
            [
                generation_id_chunk(GENERATION_ID),
                content_chunk("The notes "),
                content_chunk("list two "),
                content_chunk("open items."),
                usage_chunk(120, 40),
                done_chunk(STOP),
            ]
        ]
    )


def _v2_file_tool_round_trip() -> GraphDependencies:
    return _v2_dependencies(
        [
            [
                generation_id_chunk(GENERATION_ID),
                content_chunk("Reading the file."),
                _file_call_chunk(),
                usage_chunk(120, 40),
                done_chunk(TOOL_CALLS),
            ],
            [
                generation_id_chunk(FOLLOW_UP_GENERATION_ID),
                content_chunk("The notes "),
                content_chunk("open with a heading."),
                usage_chunk(200, 25),
                done_chunk(STOP),
            ],
        ]
    )


def _v2_catalog_tool_round_trip() -> GraphDependencies:
    return _v2_dependencies(
        [
            [
                generation_id_chunk(GENERATION_ID),
                content_chunk("Searching the web."),
                _catalog_call_chunk(),
                usage_chunk(120, 40),
                done_chunk(TOOL_CALLS),
            ],
            [
                generation_id_chunk(FOLLOW_UP_GENERATION_ID),
                content_chunk("One result "),
                content_chunk("describes the project."),
                usage_chunk(180, 30),
                done_chunk(STOP),
            ],
        ]
    )


def _v2_file_and_catalog_tools() -> GraphDependencies:
    return _v2_dependencies(
        [
            [
                generation_id_chunk(GENERATION_ID),
                content_chunk("Reading and searching."),
                _file_call_chunk(FIRST_CALL_INDEX),
                _catalog_call_chunk(SECOND_CALL_INDEX),
                usage_chunk(120, 40),
                done_chunk(TOOL_CALLS),
            ],
            [
                generation_id_chunk(FOLLOW_UP_GENERATION_ID),
                content_chunk("Both sources "),
                content_chunk("agree."),
                usage_chunk(260, 20),
                done_chunk(STOP),
            ],
        ]
    )


def _v2_provider_error() -> GraphDependencies:
    return _v2_dependencies(
        [
            [
                generation_id_chunk(GENERATION_ID),
                content_chunk("The notes "),
                content_chunk("list "),
                _provider_failure(),
            ]
        ]
    )


# --- The catalog of scenarios --------------------------------------------------


def _v1_tool_round_trip_divergences() -> Tuple[d.Divergence, ...]:
    return (
        d.v1_reports_usage_only_on_done(),
        d.v1_done_omits_generation_ids(),
        d.v1_announces_tools_only_after_they_ran(),
        d.v1_tool_results_are_tool_role_messages(),
    )


def _v2_tool_round_trip_divergences() -> Tuple[d.Divergence, ...]:
    return (
        d.v2_done_reports_tool_cost(),
        d.v2_sends_a_keepalive_before_the_first_wait(),
        d.v2_tool_calls_carry_catalog_display_names(DISPLAY_NAMES),
        d.v2_result_tool_call_is_wire_shaped(),
        d.totals_accumulate_across_generations(),
    )


def scenarios() -> List[ParityScenario]:
    """Every golden transcript, paired with the run that reproduces it."""

    return [
        ParityScenario(
            name="v1_plain_text_completion",
            build_dependencies=_v1_plain_text,
            divergences=(
                d.v1_reports_usage_only_on_done(),
                d.v1_done_omits_generation_ids(),
            ),
        ),
        ParityScenario(
            name="v1_file_tool_round_trip",
            build_dependencies=_v1_file_tool_round_trip,
            divergences=_v1_tool_round_trip_divergences()
            + (d.totals_accumulate_across_generations(),),
        ),
        ParityScenario(
            name="v1_catalog_tool_approval_gate",
            build_dependencies=_v1_catalog_tool_approval_gate,
            divergences=(
                d.v1_reports_usage_only_on_done(),
                d.v1_done_omits_generation_ids(),
            ),
        ),
        ParityScenario(
            name="v1_file_and_catalog_tools_in_one_turn",
            build_dependencies=_v1_file_and_catalog_tools,
            divergences=_v1_tool_round_trip_divergences(),
        ),
        ParityScenario(
            name="v1_provider_error_mid_stream",
            build_dependencies=_v1_provider_error,
            divergences=(d.v1_error_carries_no_detail(),),
        ),
        ParityScenario(
            name="v2_plain_text_completion",
            build_dependencies=_v2_plain_text,
            divergences=(d.v2_done_reports_tool_cost(),),
        ),
        ParityScenario(
            name="v2_file_tool_round_trip",
            build_dependencies=_v2_file_tool_round_trip,
            divergences=_v2_tool_round_trip_divergences()
            + (d.v2_shows_a_placeholder_while_a_call_streams_in(),),
        ),
        ParityScenario(
            name="v2_catalog_tool_round_trip",
            build_dependencies=_v2_catalog_tool_round_trip,
            divergences=_v2_tool_round_trip_divergences(),
        ),
        ParityScenario(
            name="v2_file_and_catalog_tools_in_one_turn",
            build_dependencies=_v2_file_and_catalog_tools,
            divergences=_v2_tool_round_trip_divergences()
            + (d.v2_shows_a_placeholder_while_a_call_streams_in(),),
        ),
        ParityScenario(
            name="v2_provider_error_mid_stream",
            build_dependencies=_v2_provider_error,
            divergences=(d.v2_error_is_labelled_generically(V2_ERROR_LABEL),),
        ),
    ]
