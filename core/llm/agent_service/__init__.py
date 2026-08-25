"""Django-side glue between a V2 chat request and `llm.agent_core`.

`llm.agent_core` is a pure agent loop: it reaches a model, a tool
catalog, a history, an approval store and a cost accountant only
through ports, and knows nothing about Django, a request, or the
format any endpoint speaks. Everything that turns one HTTP request
into a running turn lives here instead -- which stack answers the
request, which tools it may call, which key it streams on, how its
frames are rendered, and how it is billed.

The published surface is small on purpose: an endpoint decides with
`serves_agent_core`, describes the turn with `TurnRequest`, and runs
it with `V2TurnRunner`.
"""

from .dependencies import TurnRequest
from .flag import HEADER_NAME, SETTING_NAME, serves_agent_core
from .stream import ModelReroute, V2TurnRunner

__all__ = [
    "HEADER_NAME",
    "ModelReroute",
    "SETTING_NAME",
    "TurnRequest",
    "V2TurnRunner",
    "serves_agent_core",
]
