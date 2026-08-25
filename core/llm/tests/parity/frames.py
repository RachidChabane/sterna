"""The unit a parity comparison works in: one named event and its payload.

A transcript is a list of frames. Holding the payload as a decoded
mapping rather than as text is what lets a declared divergence rewrite
one field of one event and leave the rest of the transcript alone; the
frame is rendered back through `llm.agent_core.sse`, so the framing and
the field order under comparison are the adapter's, not this module's.
"""

from __future__ import annotations

import dataclasses
from typing import Any, Dict, Iterable, List, Sequence

from llm.agent_core import sse
from llm.agent_core.events import StreamEvent

JsonDict = Dict[str, Any]


@dataclasses.dataclass(frozen=True, slots=True)
class Frame:
    """One event on the wire: its name and the object on its `data:` line."""

    name: str
    payload: JsonDict

    def with_payload(self, payload: JsonDict) -> "Frame":
        return Frame(name=self.name, payload=payload)


def frames_of(events: Iterable[StreamEvent]) -> List[Frame]:
    """The frames the SSE adapter renders for a turn's events."""

    return [
        Frame(name=str(event.event_type), payload=sse.event_payload(event))
        for event in events
    ]


def render(frames: Sequence[Frame]) -> bytes:
    """The exact bytes a client reads for `frames`."""

    return "".join(
        sse.render_frame(frame.name, frame.payload) for frame in frames
    ).encode("utf-8")


def reordered(payload: JsonDict, order: Sequence[str]) -> JsonDict:
    """`payload` with the keys in `order` first, then everything else."""

    rebuilt = {name: payload[name] for name in order if name in payload}
    rebuilt.update(
        {name: value for name, value in payload.items() if name not in rebuilt}
    )
    return rebuilt


def inserted_after(payload: JsonDict, anchor: str, name: str, value: Any) -> JsonDict:
    """`payload` with `name` placed directly after `anchor`, or at the end."""

    rebuilt: JsonDict = {}
    for key, existing in payload.items():
        rebuilt[key] = existing
        if key == anchor:
            rebuilt[name] = value
    if name not in rebuilt:
        rebuilt[name] = value
    return rebuilt


def without_keys(payload: JsonDict, names: Sequence[str]) -> JsonDict:
    """`payload` without the named keys, order otherwise preserved."""

    dropped = set(names)
    return {name: value for name, value in payload.items() if name not in dropped}
