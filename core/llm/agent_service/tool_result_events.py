"""Stream events implied by what a tool call returned.

Two tool results mean more to a client than the result payload itself:
a search result carries the citations shown under the answer, and a
started preview carries the process a client can open. Neither is
something the loop can recognize -- the meaning lives in the shape of
one tool's own result -- so it asks this port.

Both derivations reuse the readers the streaming paths already share,
so a change to what a Brave result or a preview payload looks like is
made once.
"""

from __future__ import annotations

from typing import List, Sequence

from ..agent.content_sources import extract_brave_search_sources
from ..agent.sse_events import post_tool_events
from ..agent_core.events import (
    JsonDict,
    PreviewStartedEvent,
    StreamEvent,
    ToolCall,
    WebSource,
    WebSourcesEvent,
)

URL_FIELD = "url"
TITLE_FIELD = "title"
PORT_FIELD = "port"
COMMAND_FIELD = "command"
PID_FIELD = "pid"
DATA_FIELD = "data"


class V2ToolResultEvents:
    """Derives the citation and preview events one tool result implies.

    Citations are derived only for a turn that enabled web search, which
    is the condition under which the endpoint surfaces them.
    """

    def __init__(self, *, web_search_enabled: bool) -> None:
        self._web_search_enabled = web_search_enabled

    def derive(self, call: ToolCall, result: JsonDict) -> Sequence[StreamEvent]:
        entry = {
            "tool_call": {"function": {"name": call.function.name}},
            "result": result,
        }
        return self._citations(entry) + _previews(entry)

    def _citations(self, entry: JsonDict) -> List[StreamEvent]:
        if not self._web_search_enabled:
            return []
        sources = extract_brave_search_sources([entry])
        if not sources:
            return []
        return [
            WebSourcesEvent(
                sources=[
                    WebSource(url=source[URL_FIELD], title=source.get(TITLE_FIELD, ""))
                    for source in sources
                ]
            )
        ]


def _previews(entry: JsonDict) -> List[StreamEvent]:
    return [
        PreviewStartedEvent(
            port=event[DATA_FIELD].get(PORT_FIELD),
            command=event[DATA_FIELD].get(COMMAND_FIELD),
            pid=event[DATA_FIELD].get(PID_FIELD),
        )
        for event in post_tool_events([entry])
    ]
