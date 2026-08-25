"""The catalog of tools the agent execution loop can offer a model.

Defines where a tool's schema, handler, prompt snippet, display
metadata, and approval requirement are co-located and looked up by
name, so the loop and its callers share one source of truth for what
tools exist. A `ToolDefinition` never runs legacy execution logic
itself: its `handler` calls back through a `LegacyToolInvoker` port
supplied on the `ToolExecutionContext` at call time, so the module
that actually reaches a sandbox, a search API, or a Django model lives
outside this package and is wired in by whoever constructs that
context.

Entries are discovered from `llm.agent_core.tools`: every module in
that package whose name does not start with `_` must expose a
module-level `TOOL` attribute holding one `ToolDefinition`. Adding a
tool means adding one such module and nothing else — `discover_tools`
picks it up without any list to edit.
"""

from __future__ import annotations

import importlib
import pkgutil
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Awaitable, Callable, Dict, Iterable, List, Optional, Protocol

from .events import JsonDict

# --- Display and approval -----------------------------------------------


@dataclass(frozen=True, slots=True)
class ToolDisplay:
    """What the frontend shows for a tool call: a label plus an optional icon.

    `server_name`/`icon_url`/`icon_invert` are populated for a tool
    surfaced through an MCP server; a built-in tool leaves them unset.
    """

    name: str
    icon_url: Optional[str] = None
    icon_invert: bool = False
    server_name: Optional[str] = None


class ToolApproval(StrEnum):
    """Whether a tool call may run immediately or needs the user's sign-off first."""

    AUTO = "auto"
    REQUIRED = "required"


# --- Execution seam -------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ToolExecutionContext:
    """The request-scoped values a tool handler needs to run a call.

    `invoker` is the port through which a handler reaches whatever
    owns the real execution logic for legacy tools (an HTTP call to
    the sandbox orchestrator, an MCP server, a Django-backed service);
    this package never implements that logic itself.
    """

    user_id: str
    conversation_id: str
    invoker: "LegacyToolInvoker"
    chat_id: Optional[str] = None
    sync_mode: bool = True
    extra: JsonDict = field(default_factory=dict)


class LegacyToolInvoker(Protocol):
    """The port a `ToolDefinition.handler` calls back through to run legacy logic.

    Implemented outside `agent_core` by whatever owns the Django-aware
    or LangChain-aware execution path for a given tool id, and passed
    in on the `ToolExecutionContext` at call time.
    """

    async def invoke(
        self, tool_id: str, arguments: JsonDict, context: ToolExecutionContext
    ) -> JsonDict:
        ...


ToolHandler = Callable[[JsonDict, ToolExecutionContext], Awaitable[JsonDict]]


# --- Definition -------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    """Everything the execution loop needs to offer and run one tool."""

    id: str
    display: ToolDisplay
    description: str
    input_schema: JsonDict
    handler: ToolHandler
    approval: ToolApproval
    prompt_snippet: Optional[str] = None

    def to_openai_function(self) -> JsonDict:
        """This tool's entry in an OpenAI-shaped `tools` request parameter."""

        return {
            "type": "function",
            "function": {
                "name": self.id,
                "description": self.description,
                "parameters": self.input_schema,
            },
        }


# --- Discovery and lookup ----------------------------------------------


TOOLS_PACKAGE = "llm.agent_core.tools"


def discover_tools(package_name: str = TOOLS_PACKAGE) -> Dict[str, ToolDefinition]:
    """Import every public module under `package_name` and collect its `TOOL`.

    A module whose name starts with `_` is a shared helper, not a tool
    entry, and is skipped.
    """

    package = importlib.import_module(package_name)
    found: Dict[str, ToolDefinition] = {}
    for module_info in pkgutil.iter_modules(package.__path__):
        if module_info.name.startswith("_"):
            continue
        module = importlib.import_module(f"{package_name}.{module_info.name}")
        tool = getattr(module, "TOOL", None)
        if not isinstance(tool, ToolDefinition):
            raise TypeError(
                f"{package_name}.{module_info.name} must define a module-level "
                f"TOOL: ToolDefinition; found {type(tool).__name__ if tool is not None else None}"
            )
        if tool.id in found:
            raise ValueError(
                f"duplicate tool id {tool.id!r}: defined in both "
                f"{found[tool.id].display.name!r} and {module_info.name!r}"
            )
        found[tool.id] = tool
    return found


class ToolRegistry:
    """A lookup of `ToolDefinition`s by id, closed over at construction time."""

    def __init__(self, definitions: Iterable[ToolDefinition]):
        self._by_id: Dict[str, ToolDefinition] = {}
        for definition in definitions:
            if definition.id in self._by_id:
                raise ValueError(f"duplicate tool id: {definition.id!r}")
            self._by_id[definition.id] = definition

    @classmethod
    def discover(cls, package_name: str = TOOLS_PACKAGE) -> "ToolRegistry":
        return cls(discover_tools(package_name).values())

    def get(self, tool_id: str) -> Optional[ToolDefinition]:
        return self._by_id.get(tool_id)

    def all(self) -> List[ToolDefinition]:
        return list(self._by_id.values())

    def __contains__(self, tool_id: str) -> bool:
        return tool_id in self._by_id

    def __len__(self) -> int:
        return len(self._by_id)

    def to_openai_functions(self) -> List[JsonDict]:
        return [tool.to_openai_function() for tool in self._by_id.values()]
