"""The declared differences between the agent loop's stream and a legacy one.

A parity comparison rewrites what the loop emitted into what the legacy
loop would have emitted, then compares that to the committed golden
transcript byte for byte. Every rewrite is one `Divergence` named here,
carrying the reason the difference cannot be closed by the SSE adapter,
and each one a scenario declares must change that scenario's frames --
a rule that no longer applies fails rather than passing unnoticed.

Two classes of difference live here. Most are legacy artifacts the loop
does not reproduce: an event only one of the two legacy paths ever
sent, a placeholder emitted before there was anything to show, a
keep-alive sent before the first wait, totals accumulated across a
turn's generations. The rest -- `display_name` never merged in from the
catalog, and the dataclass field order and unset optionals of an
embedded tool call -- are gaps in the loop itself rather than legacy
quirks.

A rewrite reads the figures it needs from `emitted`, the frames the
loop produced before any rewrite ran, so no rule depends on which
other rules already applied.
"""

from __future__ import annotations

import dataclasses
import json
from typing import Any, Callable, Dict, List, Mapping, Sequence

from llm.agent_core.events import EventType

from .frames import Frame, inserted_after, reordered, without_keys

Rewrite = Callable[[Sequence[Frame], Sequence[Frame]], List[Frame]]
"""Rewrites the current frames, given the frames the loop first emitted."""

USAGE_UPDATE = str(EventType.USAGE_UPDATE)
DONE = str(EventType.DONE)
ERROR = str(EventType.ERROR)
HEARTBEAT = str(EventType.HEARTBEAT)
FILE_TOOL_EXECUTING = str(EventType.FILE_TOOL_EXECUTING)
FILE_TOOL_EXECUTED = str(EventType.FILE_TOOL_EXECUTED)

TOOL_CALLS_FIELD = "tool_calls"
RESULTS_FIELD = "results"
TOOL_CALL_FIELD = "tool_call"
RESULT_FIELD = "result"
USAGE_FIELD = "usage"
COST_FIELD = "cost"
PROMPT_COST_FIELD = "prompt_cost"
COMPLETION_COST_FIELD = "completion_cost"
TOOL_COST_FIELD = "tool_cost"
GENERATION_ID_FIELD = "generation_id"
GENERATION_IDS_FIELD = "generation_ids"
DETAIL_FIELD = "detail"
ERROR_FIELD = "error"
DISPLAY_NAME_FIELD = "display_name"
ELAPSED_SECONDS_FIELD = "elapsed_seconds"
TOOL_FIELD = "tool"
ID_FIELD = "id"
TYPE_FIELD = "type"
FUNCTION_FIELD = "function"
NAME_FIELD = "name"

PROMPT_TOKENS = "prompt_tokens"
COMPLETION_TOKENS = "completion_tokens"
TOTAL_TOKENS = "total_tokens"

TOOL_ROLE = "tool"
ROLE_FIELD = "role"
TOOL_CALL_ID_FIELD = "tool_call_id"
CONTENT_FIELD = "content"

NO_TOOL_COST = 0.0
FIRST_KEEPALIVE_ELAPSED_SECONDS = 0

LOADING_PLACEHOLDER_CALL: Dict[str, Any] = {
    "function": {"name": "...", "arguments": "{}"},
    "id": "loading",
    "type": "function",
}
"""The stand-in call the legacy V2 loop shows while a real one streams in."""

WIRE_TOOL_CALL_ORDER = (ID_FIELD, TYPE_FIELD, FUNCTION_FIELD)


@dataclasses.dataclass(frozen=True, slots=True)
class Divergence:
    """One declared difference, with the reason it is not the adapter's to close."""

    name: str
    reason: str
    rewrite: Rewrite

    def applied_to(
        self, frames: Sequence[Frame], emitted: Sequence[Frame]
    ) -> List[Frame]:
        return self.rewrite(frames, emitted)


# --- Helpers ---------------------------------------------------------------


def _mapping_each(
    frames: Sequence[Frame], name: str, change: Callable[[Frame], Frame]
) -> List[Frame]:
    return [change(frame) if frame.name == name else frame for frame in frames]


def _usage_totals(emitted: Sequence[Frame]) -> List[Mapping[str, float]]:
    """The running totals of a turn, one entry per generation that reported usage."""

    totals: List[Mapping[str, float]] = []
    running: Dict[str, float] = {
        PROMPT_TOKENS: 0,
        COMPLETION_TOKENS: 0,
        TOTAL_TOKENS: 0,
        COST_FIELD: 0.0,
        PROMPT_COST_FIELD: 0.0,
        COMPLETION_COST_FIELD: 0.0,
    }
    for frame in emitted:
        if frame.name != USAGE_UPDATE:
            continue
        usage = frame.payload[USAGE_FIELD]
        running = {
            PROMPT_TOKENS: running[PROMPT_TOKENS] + usage[PROMPT_TOKENS],
            COMPLETION_TOKENS: running[COMPLETION_TOKENS] + usage[COMPLETION_TOKENS],
            TOTAL_TOKENS: running[TOTAL_TOKENS] + usage[TOTAL_TOKENS],
            COST_FIELD: running[COST_FIELD] + frame.payload[COST_FIELD],
            PROMPT_COST_FIELD: running[PROMPT_COST_FIELD]
            + frame.payload[PROMPT_COST_FIELD],
            COMPLETION_COST_FIELD: running[COMPLETION_COST_FIELD]
            + frame.payload[COMPLETION_COST_FIELD],
        }
        totals.append(running)
    return totals


def _with_totals(
    payload: Mapping[str, Any], totals: Mapping[str, float]
) -> Dict[str, Any]:
    rewritten: Dict[str, Any] = dict(payload)
    rewritten[USAGE_FIELD] = {
        PROMPT_TOKENS: totals[PROMPT_TOKENS],
        COMPLETION_TOKENS: totals[COMPLETION_TOKENS],
        TOTAL_TOKENS: totals[TOTAL_TOKENS],
    }
    for field in (COST_FIELD, PROMPT_COST_FIELD, COMPLETION_COST_FIELD):
        if field in rewritten:
            rewritten[field] = totals[field]
    return rewritten


# --- V1 divergences ---------------------------------------------------------


def v1_reports_usage_only_on_done() -> Divergence:
    def rewrite(frames: Sequence[Frame], _emitted: Sequence[Frame]) -> List[Frame]:
        return [frame for frame in frames if frame.name != USAGE_UPDATE]

    return Divergence(
        name="v1_reports_usage_only_on_done",
        reason=(
            "The V1 stream carries token and cost figures only on its terminal "
            "done event. The loop surfaces the provider's usage chunk as a "
            "usage_update the moment it arrives, so a client that stops reading "
            "early still has figures."
        ),
        rewrite=rewrite,
    )


def v1_done_omits_generation_ids() -> Divergence:
    def rewrite(frames: Sequence[Frame], _emitted: Sequence[Frame]) -> List[Frame]:
        return _mapping_each(
            frames,
            DONE,
            lambda frame: frame.with_payload(
                without_keys(frame.payload, (GENERATION_ID_FIELD, GENERATION_IDS_FIELD))
            ),
        )

    return Divergence(
        name="v1_done_omits_generation_ids",
        reason=(
            "The V1 done event reports the model, the finish reason and the "
            "totals only. The loop also reports which provider generations the "
            "turn spanned, which is what a caller needs to reconcile billing "
            "for a turn that called tools."
        ),
        rewrite=rewrite,
    )


def v1_announces_tools_only_after_they_ran() -> Divergence:
    def rewrite(frames: Sequence[Frame], _emitted: Sequence[Frame]) -> List[Frame]:
        return [frame for frame in frames if frame.name != FILE_TOOL_EXECUTING]

    return Divergence(
        name="v1_announces_tools_only_after_they_ran",
        reason=(
            "The V1 loop runs its file tools synchronously and announces them "
            "once, after they have finished. The loop announces the round as it "
            "starts, so the frontend can show work in progress."
        ),
        rewrite=rewrite,
    )


def v1_tool_results_are_tool_role_messages() -> Divergence:
    def _rewrite_frame(frame: Frame) -> Frame:
        results = [
            {
                ROLE_FIELD: TOOL_ROLE,
                TOOL_CALL_ID_FIELD: entry[TOOL_CALL_FIELD][ID_FIELD],
                NAME_FIELD: entry[TOOL_CALL_FIELD][FUNCTION_FIELD][NAME_FIELD],
                CONTENT_FIELD: json.dumps(entry[RESULT_FIELD]),
            }
            for entry in frame.payload[RESULTS_FIELD]
        ]
        return frame.with_payload({**frame.payload, RESULTS_FIELD: results})

    def rewrite(frames: Sequence[Frame], _emitted: Sequence[Frame]) -> List[Frame]:
        return _mapping_each(frames, FILE_TOOL_EXECUTED, _rewrite_frame)

    return Divergence(
        name="v1_tool_results_are_tool_role_messages",
        reason=(
            "V1 puts the OpenAI tool-role messages it will send back to the "
            "model on the wire; V2 puts a call/result/success triple there. The "
            "two legacy paths disagree, the loop adopted V2's shape, and no "
            "adapter can satisfy both."
        ),
        rewrite=rewrite,
    )


def v1_error_carries_no_detail() -> Divergence:
    def rewrite(frames: Sequence[Frame], _emitted: Sequence[Frame]) -> List[Frame]:
        return _mapping_each(
            frames,
            ERROR,
            lambda frame: frame.with_payload(
                without_keys(frame.payload, (DETAIL_FIELD,))
            ),
        )

    return Divergence(
        name="v1_error_carries_no_detail",
        reason=(
            "V1 reports a failed generation as a bare user-facing sentence. The "
            "loop keeps the provider's own message alongside it as detail, so "
            "the operator-facing text is not lost."
        ),
        rewrite=rewrite,
    )


# --- V2 divergences ---------------------------------------------------------


def v2_error_is_labelled_generically(label: str) -> Divergence:
    def rewrite(frames: Sequence[Frame], _emitted: Sequence[Frame]) -> List[Frame]:
        return _mapping_each(
            frames,
            ERROR,
            lambda frame: frame.with_payload({**frame.payload, ERROR_FIELD: label}),
        )

    return Divergence(
        name="v2_error_is_labelled_generically",
        reason=(
            f"V2 labels every mid-stream failure {label!r} and leaves the "
            "provider's message in detail. The loop maps the provider error "
            "class to a sentence written for the person waiting on the answer, "
            "so the two paths cannot both be satisfied."
        ),
        rewrite=rewrite,
    )


def v2_done_reports_tool_cost() -> Divergence:
    def rewrite(frames: Sequence[Frame], _emitted: Sequence[Frame]) -> List[Frame]:
        return _mapping_each(
            frames,
            DONE,
            lambda frame: frame.with_payload(
                inserted_after(
                    frame.payload,
                    COMPLETION_COST_FIELD,
                    TOOL_COST_FIELD,
                    NO_TOOL_COST,
                )
            ),
        )

    return Divergence(
        name="v2_done_reports_tool_cost",
        reason=(
            "V2 bills tool invocations separately from the generation and "
            "reports that figure on done. The loop has no tool-cost concept and "
            "no port to obtain one from, so it reports no such field."
        ),
        rewrite=rewrite,
    )


def v2_shows_a_placeholder_while_a_call_streams_in() -> Divergence:
    def rewrite(frames: Sequence[Frame], _emitted: Sequence[Frame]) -> List[Frame]:
        rewritten: List[Frame] = []
        placed = False
        for frame in frames:
            if not placed and frame.name == USAGE_UPDATE:
                rewritten.append(
                    Frame(
                        name=FILE_TOOL_EXECUTING,
                        payload={TOOL_CALLS_FIELD: [dict(LOADING_PLACEHOLDER_CALL)]},
                    )
                )
                placed = True
            rewritten.append(frame)
        return rewritten

    return Divergence(
        name="v2_shows_a_placeholder_while_a_call_streams_in",
        reason=(
            "With file tools enabled, V2 emits a file_tool_executing carrying a "
            "stand-in call the moment the first tool-call fragment arrives -- in "
            "these fixtures, between the last content chunk and the usage chunk. "
            "The loop emits file_tool_executing once, when the calls it names "
            "actually start."
        ),
        rewrite=rewrite,
    )


def v2_sends_a_keepalive_before_the_first_wait() -> Divergence:
    def _keepalives(frame: Frame) -> List[Frame]:
        return [
            Frame(
                name=HEARTBEAT,
                payload={
                    TOOL_FIELD: call[FUNCTION_FIELD][NAME_FIELD],
                    ELAPSED_SECONDS_FIELD: FIRST_KEEPALIVE_ELAPSED_SECONDS,
                },
            )
            for call in frame.payload[TOOL_CALLS_FIELD]
        ]

    def rewrite(frames: Sequence[Frame], _emitted: Sequence[Frame]) -> List[Frame]:
        rewritten: List[Frame] = []
        for frame in frames:
            if frame.name == FILE_TOOL_EXECUTED:
                rewritten.extend(_keepalives(frame))
            rewritten.append(frame)
        return rewritten

    return Divergence(
        name="v2_sends_a_keepalive_before_the_first_wait",
        reason=(
            "V2 polls each tool task in a loop that emits a keep-alive before it "
            "first waits, so even a tool that returns immediately produces one. "
            "The loop's keep-alive fires only once its interval has actually "
            "elapsed, which is what makes its transcript reproducible."
        ),
        rewrite=rewrite,
    )


def v2_tool_calls_carry_catalog_display_names(
    display_names: Mapping[str, str],
) -> Divergence:
    def _named(call: Mapping[str, Any]) -> Dict[str, Any]:
        name = call[FUNCTION_FIELD][NAME_FIELD]
        return {**call, DISPLAY_NAME_FIELD: display_names[name]}

    def _rewrite_frame(frame: Frame) -> Frame:
        return frame.with_payload(
            {
                **frame.payload,
                TOOL_CALLS_FIELD: [_named(call) for call in frame.payload[TOOL_CALLS_FIELD]],
            }
        )

    def rewrite(frames: Sequence[Frame], _emitted: Sequence[Frame]) -> List[Frame]:
        announced = _mapping_each(frames, FILE_TOOL_EXECUTING, _rewrite_frame)
        return _mapping_each(announced, FILE_TOOL_EXECUTED, _rewrite_frame)

    return Divergence(
        name="v2_tool_calls_carry_catalog_display_names",
        reason=(
            "V2 enriches each announced call with the label its catalog holds. "
            "The loop streams the call as the provider spelled it and never "
            "merges the registry's display metadata in -- a gap in the loop "
            "rather than a legacy quirk."
        ),
        rewrite=rewrite,
    )


def v2_result_tool_call_is_wire_shaped() -> Divergence:
    def _wire_shaped(entry: Mapping[str, Any]) -> Dict[str, Any]:
        call = {
            field: value
            for field, value in entry[TOOL_CALL_FIELD].items()
            if value is not None
        }
        return {**entry, TOOL_CALL_FIELD: reordered(call, WIRE_TOOL_CALL_ORDER)}

    def _rewrite_frame(frame: Frame) -> Frame:
        return frame.with_payload(
            {
                **frame.payload,
                RESULTS_FIELD: [
                    _wire_shaped(entry) for entry in frame.payload[RESULTS_FIELD]
                ],
            }
        )

    def rewrite(frames: Sequence[Frame], _emitted: Sequence[Frame]) -> List[Frame]:
        return _mapping_each(frames, FILE_TOOL_EXECUTED, _rewrite_frame)

    return Divergence(
        name="v2_result_tool_call_is_wire_shaped",
        reason=(
            "The call embedded in a result entry reaches the wire through "
            "dataclasses.asdict, which puts the fields in declaration order and "
            "sends the three unset display fields as null. V2 emits the wire "
            "shape -- a gap in the loop rather than a legacy quirk."
        ),
        rewrite=rewrite,
    )


# --- Shared divergences ------------------------------------------------------


def totals_accumulate_across_generations() -> Divergence:
    def rewrite(frames: Sequence[Frame], emitted: Sequence[Frame]) -> List[Frame]:
        totals = _usage_totals(emitted)
        if not totals:
            return list(frames)
        rewritten: List[Frame] = []
        generation = 0
        for frame in frames:
            if frame.name == USAGE_UPDATE:
                rewritten.append(
                    frame.with_payload(_with_totals(frame.payload, totals[generation]))
                )
                generation += 1
            elif frame.name == DONE:
                rewritten.append(
                    frame.with_payload(_with_totals(frame.payload, totals[-1]))
                )
            else:
                rewritten.append(frame)
        return rewritten

    return Divergence(
        name="totals_accumulate_across_generations",
        reason=(
            "Both legacy paths report the running totals of the whole turn, so a "
            "turn that called tools bills for every generation it took. The "
            "loop's accounting is per generation by design: the done event "
            "reports the last generation's figures alongside the ids of all of "
            "them."
        ),
        rewrite=rewrite,
    )
