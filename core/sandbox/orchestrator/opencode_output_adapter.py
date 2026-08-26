"""Translate the opencode run stream into the progress-store payload.

``opencode run --format json`` prints one JSON object per line. The
shapes this adapter consumes:

``{"type": "step_start", "part": {"type": "step-start", ...}}``
    Opens an assistant step.
``{"type": "text", "part": {"type": "text", "text": ...}}``
    Assistant prose within the open step.
``{"type": "tool_use", "part": {"type": "tool", "tool": ..., "callID":
..., "state": {"status": ..., "input": {...}, "output": ...}}}``
    One tool call *and* its result, collapsed into a single line.
``{"type": "step_finish", "part": {"type": "step-finish", "tokens":
{...}, "cost": ...}}``
    Closes the step and reports that step's usage.

The stream is bracketed by two lines the in-sandbox wrapper prints —
``system`` before the run and ``result`` after it — so a recorded
stream carries everything the payload needs, with no out-of-band state.

Three translations turn that into the payload the chat layer polls:

Vocabulary
    opencode names tools in lower case (``read``) and MCP tools as
    ``{server}_{tool}``; the payload's names are ``Read`` and
    ``mcp__{server}__{tool}``. Tool inputs are renamed from opencode's
    camelCase to the payload's snake_case, and paths are made relative
    to the workspace root.

Step ordering
    One ``tool_use`` line yields two payload steps, a ``tool_call`` and
    the ``tool_result`` that follows it, the second released when the
    step closes. Within one assistant step the tool call precedes the
    prose, so a text part is held until the step's first tool call is
    emitted (or the step closes without one).

Usage
    Every ``step_finish`` reports that step's token counts and its cost
    in USD, which opencode prices from the model's catalogue entry. Cost
    accrues into ``running_cost_usd`` as each step closes, so a budget
    check has a real figure to read while the run is still going. The
    payload's own usage fields are published only when the run ends —
    ``total_cost_usd`` as the session total, ``total_tokens`` as the
    final step's own input plus output — so a poll taken mid-run never
    shows a partial figure the chat layer would have to reconcile.
"""

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Mapping, Optional, Set, Tuple

logger = logging.getLogger(__name__)

# Line types opencode and the wrapper emit.
LINE_SYSTEM = "system"
LINE_STEP_START = "step_start"
LINE_STEP_FINISH = "step_finish"
LINE_TEXT = "text"
LINE_TOOL_USE = "tool_use"
LINE_RESULT = "result"

# Step types in the progress payload.
STEP_SYSTEM = "system"
STEP_TEXT = "text"
STEP_TOOL_CALL = "tool_call"
STEP_TOOL_RESULT = "tool_result"
STEP_RESULT = "result"
STEP_ERROR = "error"

TOOL_STATUS_ERROR = "error"

# opencode marks a call the model made against a tool it was not offered.
INVALID_TOOL = "invalid"

# Summing per-step costs in binary floating point leaves drift well
# below a millionth of a cent; the total is rounded back onto the grid
# the per-step figures came from.
COST_PRECISION_DECIMALS = 10

# opencode's read tool returns a numbered listing wrapped in tags rather
# than the file's bytes. These bracket the part that is the file.
READ_CONTENT_OPEN = "<content>"
READ_CONTENT_CLOSE = "</content>"
READ_EOF_MARKER = "(End of file"


@dataclass
class OpencodeStep:
    """One entry in the progress payload's ``steps`` list."""

    type: str
    tool: Optional[str] = None
    content: Optional[str] = None
    input: Optional[Dict[str, Any]] = None
    output: Optional[str] = None


class PathNormalizer:
    """Rewrites absolute sandbox paths as workspace-relative ones.

    opencode reports the paths it resolved, which are absolute; the
    payload carries the paths a reader of the chat sees, which are
    relative to the workspace root.
    """

    def __init__(self, workspace_root: str = "") -> None:
        self.workspace_root = workspace_root.rstrip("/")

    def relative(self, path: str) -> str:
        if not path:
            return path
        if self.workspace_root and path.startswith(self.workspace_root + "/"):
            path = path[len(self.workspace_root) + 1:]
        if path.startswith("./"):
            path = path[2:]
        return path

    def relative_lines(self, text: str) -> str:
        return "\n".join(self.relative(line) for line in text.split("\n"))

    def is_inside(self, path: str) -> bool:
        """Whether a path the agent touched lies within the workspace.

        A relative path is resolved against the workspace and so always
        does; an absolute one only if it descends from the root.
        """
        if not path.startswith("/"):
            return True
        return bool(self.workspace_root) and path.startswith(self.workspace_root + "/")


ResultRenderer = Callable[[Dict[str, Any], Dict[str, Any], PathNormalizer], str]


def _render_raw(state: Dict[str, Any], _input: Dict[str, Any], _paths: PathNormalizer) -> str:
    return str(state.get("output") or "")


def _render_path_list(state: Dict[str, Any], _input: Dict[str, Any], paths: PathNormalizer) -> str:
    return paths.relative_lines(str(state.get("output") or ""))


def _render_read(state: Dict[str, Any], _input: Dict[str, Any], _paths: PathNormalizer) -> str:
    """Rebuild the file's text from opencode's numbered listing.

    The listing enumerates the file's lines, so rejoining them and
    terminating the last one reproduces the file as stored.
    """
    output = str(state.get("output") or "")
    start = output.find(READ_CONTENT_OPEN)
    end = output.find(READ_CONTENT_CLOSE)
    if start < 0 or end < 0:
        return output

    body = output[start + len(READ_CONTENT_OPEN):end]
    lines: List[str] = []
    for raw in body.split("\n"):
        if not raw.strip() or raw.lstrip().startswith(READ_EOF_MARKER):
            continue
        number, separator, text = raw.partition(":")
        if not separator or not number.strip().isdigit():
            lines.append(raw)
            continue
        lines.append(text[1:] if text.startswith(" ") else text)
    if not lines:
        return ""
    return "\n".join(lines) + "\n"


def _render_write(state: Dict[str, Any], tool_input: Dict[str, Any], paths: PathNormalizer) -> str:
    path = paths.relative(str(tool_input.get("file_path") or ""))
    existed = bool((state.get("metadata") or {}).get("exists"))
    if existed:
        return f"The file {path} has been updated."
    return f"File created successfully at: {path}"


def _render_edit(_state: Dict[str, Any], tool_input: Dict[str, Any], paths: PathNormalizer) -> str:
    path = paths.relative(str(tool_input.get("file_path") or ""))
    return f"The file {path} has been updated."


@dataclass(frozen=True)
class ToolTranslation:
    """How one opencode tool maps onto the payload's vocabulary."""

    canonical_name: str
    input_keys: Mapping[str, str] = field(default_factory=dict)
    render_result: ResultRenderer = _render_raw


_PATH_INPUT = {"filePath": "file_path"}

#: Built-in opencode tools, keyed by the name opencode reports.
TOOL_TRANSLATIONS: Mapping[str, ToolTranslation] = {
    "read": ToolTranslation("Read", {**_PATH_INPUT, "offset": "offset", "limit": "limit"}, _render_read),
    "write": ToolTranslation("Write", {**_PATH_INPUT, "content": "content"}, _render_write),
    "edit": ToolTranslation(
        "Edit",
        {
            **_PATH_INPUT,
            "oldString": "old_string",
            "newString": "new_string",
            "replaceAll": "replace_all",
        },
        _render_edit,
    ),
    "patch": ToolTranslation("Edit", {**_PATH_INPUT, "patch": "patch"}, _render_edit),
    "glob": ToolTranslation("Glob", {"pattern": "pattern", "path": "path"}, _render_path_list),
    "grep": ToolTranslation(
        "Grep", {"pattern": "pattern", "path": "path", "include": "include"}, _render_path_list
    ),
    "list": ToolTranslation("LS", {"path": "path", "ignore": "ignore"}, _render_path_list),
    "bash": ToolTranslation("Bash", {"command": "command", "description": "description"}),
    "task": ToolTranslation("Task", {"description": "description", "prompt": "prompt"}),
    "todowrite": ToolTranslation("TodoWrite", {"todos": "todos"}),
    "webfetch": ToolTranslation("WebFetch", {"url": "url", "format": "format"}),
}

#: Payload tool name to the opencode tool it names, derived from
#: `TOOL_TRANSLATIONS` so one table defines the vocabulary in both
#: directions. Where two opencode tools share a payload name — ``edit``
#: and ``patch`` are both ``Edit`` — the first one declared wins.
_PAYLOAD_TO_OPENCODE: Dict[str, str] = {}
for _opencode_name, _translation in TOOL_TRANSLATIONS.items():
    _PAYLOAD_TO_OPENCODE.setdefault(_translation.canonical_name, _opencode_name)

#: How the payload spells an MCP tool, against opencode's ``{server}_{tool}``.
MCP_PAYLOAD_PREFIX = "mcp__"
MCP_PAYLOAD_SEPARATOR = "__"


def opencode_tool_name(payload_name: str) -> Optional[str]:
    """The opencode tool a payload tool name refers to, or None.

    The inverse of what `OpencodeOutputAdapter` does to a run's stream,
    for the places that must hand opencode a tool name of its own — a
    permission rule, say — starting from the payload's vocabulary. A
    name with no opencode counterpart yields None rather than a guess.
    """
    if payload_name.startswith(MCP_PAYLOAD_PREFIX):
        server, separator, tool = payload_name[len(MCP_PAYLOAD_PREFIX):].partition(
            MCP_PAYLOAD_SEPARATOR
        )
        return f"{server}_{tool}" if separator and server and tool else None
    return _PAYLOAD_TO_OPENCODE.get(payload_name)


# Payload tool names that move a file, mirroring the Claude harness's
# classification so both harnesses fill the same four file lists.
WRITE_TOOLS = {"Write"}
EDIT_TOOLS = {"Edit"}
READ_TOOLS = {"Read"}


class OpencodeOutputAdapter:
    """Accumulates one opencode run into the progress payload's fields."""

    def __init__(self, workspace_path: str = "", mcp_servers: Optional[List[str]] = None) -> None:
        self.steps: List[OpencodeStep] = []
        self.files_created: Set[str] = set()
        self.files_modified: Set[str] = set()
        self.files_read: Set[str] = set()
        self.files_deleted: Set[str] = set()
        self.error: Optional[str] = None
        self.summary: Optional[str] = None
        self.total_cost_usd: float = 0.0
        self.total_tokens: int = 0
        self.running_cost_usd: float = 0.0

        self._paths = PathNormalizer(workspace_path)
        self._mcp_servers: List[str] = sorted(mcp_servers or [], key=len, reverse=True)
        self._pending_text: List[OpencodeStep] = []
        self._pending_results: List[OpencodeStep] = []
        self._accrued_cost: float = 0.0
        self._last_step_tokens: int = 0

    # -- port -----------------------------------------------------------

    def ingest(self, line: str) -> bool:
        """Consume one output line; report whether it produced a step."""
        stripped = line.strip()
        if not stripped:
            return False
        try:
            event = json.loads(stripped)
        except json.JSONDecodeError as exc:
            logger.warning(f"[Opencode] Failed to parse JSON line: {exc}")
            return False
        if not isinstance(event, dict):
            return False

        produced = self._handle(event)
        self.steps.extend(produced)
        return bool(produced)

    # -- line handlers --------------------------------------------------

    def _handle(self, event: Dict[str, Any]) -> List[OpencodeStep]:
        line_type = event.get("type", "")
        if line_type == LINE_SYSTEM:
            return self._on_system(event)
        if line_type == LINE_TEXT:
            return self._on_text(event)
        if line_type == LINE_TOOL_USE:
            return self._on_tool_use(event)
        if line_type == LINE_STEP_FINISH:
            return self._on_step_finish(event)
        if line_type == LINE_RESULT:
            return self._on_result(event)
        if line_type == LINE_STEP_START:
            return []
        logger.debug(f"[Opencode] Unhandled line type: {line_type}")
        return []

    def _on_system(self, event: Dict[str, Any]) -> List[OpencodeStep]:
        cwd = event.get("cwd")
        if cwd:
            self._paths = PathNormalizer(str(cwd))
        servers = event.get("mcp_servers")
        if isinstance(servers, list):
            self._mcp_servers = sorted((str(s) for s in servers), key=len, reverse=True)
        return [OpencodeStep(type=STEP_SYSTEM, content=f"System: {event.get('subtype', '')}")]

    def _on_text(self, event: Dict[str, Any]) -> List[OpencodeStep]:
        text = str((event.get("part") or {}).get("text") or "")
        if text:
            self._pending_text.append(OpencodeStep(type=STEP_TEXT, content=text))
        return []

    def _on_tool_use(self, event: Dict[str, Any]) -> List[OpencodeStep]:
        part = event.get("part") or {}
        state = part.get("state") or {}
        raw_input = state.get("input") if isinstance(state.get("input"), dict) else {}

        canonical, translation = self._translate_tool(str(part.get("tool") or ""), raw_input)
        tool_input = self._translate_input(raw_input, translation)

        call = OpencodeStep(
            type=STEP_TOOL_CALL,
            tool=canonical,
            content=f"Using {canonical}",
            input=tool_input,
        )
        # The line reports the call's outcome alongside it, so a
        # refused or failed call never counts as a file change.
        if state.get("status") != TOOL_STATUS_ERROR:
            self._track_file_operation(canonical, tool_input)
        self._pending_results.append(self._build_result_step(state, tool_input, translation))

        # The tool call leads its step; prose the model emitted first
        # follows it, mirroring how the payload has always ordered them.
        return [call] + self._drain(self._pending_text)

    def _on_step_finish(self, event: Dict[str, Any]) -> List[OpencodeStep]:
        part = event.get("part") or {}
        cost = part.get("cost")
        if isinstance(cost, (int, float)):
            self._accrued_cost += float(cost)
            self.running_cost_usd = round(self._accrued_cost, COST_PRECISION_DECIMALS)
        tokens = part.get("tokens")
        if isinstance(tokens, dict):
            self._last_step_tokens = int(tokens.get("input", 0) or 0) + int(
                tokens.get("output", 0) or 0
            )
        return self._drain(self._pending_results) + self._drain(self._pending_text)

    def _on_result(self, event: Dict[str, Any]) -> List[OpencodeStep]:
        released = self._drain(self._pending_results) + self._drain(self._pending_text)

        self.total_cost_usd = self.running_cost_usd
        self.total_tokens = self._last_step_tokens

        error = event.get("error")
        if error:
            self.error = str(error)
            return released + [OpencodeStep(type=STEP_ERROR, content=self.error)]

        self.summary = event.get("result") or ""
        return released + [OpencodeStep(type=STEP_RESULT, content=self.summary)]

    # -- translation ----------------------------------------------------

    def _translate_tool(
        self, opencode_name: str, raw_input: Dict[str, Any]
    ) -> Tuple[str, Optional[ToolTranslation]]:
        """Resolve one opencode tool name to its payload name."""
        if opencode_name == INVALID_TOOL:
            # opencode reports the name the model reached for in the input.
            attempted = str(raw_input.get("tool") or INVALID_TOOL)
            return self._translate_tool(attempted, {})[0], None

        translation = TOOL_TRANSLATIONS.get(opencode_name)
        if translation is not None:
            return translation.canonical_name, translation

        for server in self._mcp_servers:
            prefix = f"{server}_"
            if opencode_name.startswith(prefix):
                return f"mcp__{server}__{opencode_name[len(prefix):]}", None

        return opencode_name, None

    @staticmethod
    def _translate_input(
        raw_input: Dict[str, Any], translation: Optional[ToolTranslation]
    ) -> Dict[str, Any]:
        if translation is None:
            return dict(raw_input)
        renamed: Dict[str, Any] = {}
        for key, value in raw_input.items():
            renamed[translation.input_keys.get(key, key)] = value
        return renamed

    def _build_result_step(
        self,
        state: Dict[str, Any],
        tool_input: Dict[str, Any],
        translation: Optional[ToolTranslation],
    ) -> OpencodeStep:
        if state.get("status") == TOOL_STATUS_ERROR:
            rendered = str(state.get("error") or "")
        else:
            render = translation.render_result if translation else _render_raw
            rendered = render(state, tool_input, self._paths)
        return OpencodeStep(type=STEP_TOOL_RESULT, content=rendered or None, output=rendered or None)

    @staticmethod
    def _drain(pending: List[OpencodeStep]) -> List[OpencodeStep]:
        released = list(pending)
        pending.clear()
        return released

    def _track_file_operation(self, canonical_tool: str, tool_input: Dict[str, Any]) -> None:
        """Record a change to a workspace file.

        The four file lists describe the user's workspace. A path
        outside it — the plans directory a planning run writes into,
        for one — is the harness's own bookkeeping, not a change the
        user made and can review.
        """
        raw_path = str(tool_input.get("file_path") or tool_input.get("path") or "")
        if not raw_path or not self._paths.is_inside(raw_path):
            return
        path = self._paths.relative(raw_path)

        if canonical_tool in WRITE_TOOLS:
            if path in self.files_read:
                self.files_modified.add(path)
            else:
                self.files_created.add(path)
        elif canonical_tool in EDIT_TOOLS:
            self.files_modified.add(path)
            self.files_created.discard(path)
        elif canonical_tool in READ_TOOLS:
            self.files_read.add(path)
