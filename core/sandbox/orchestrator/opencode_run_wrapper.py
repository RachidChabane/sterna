#!/usr/bin/env python3
"""Run opencode inside the sandbox and bracket its output stream.

``opencode run --format json`` prints one JSON object per step of the
turn, and nothing around them: no line announcing the run, and none
carrying the run's outcome. The progress payload needs both, so this
wrapper prints them itself and passes opencode's own lines through
untouched.

The opening ``system`` line names the workspace root, the model, the
tools and the MCP servers, which is what lets a recorded stream be
replayed without knowing anything else about the job. The closing
``result`` line carries the run's summary: for a planning run the plan
the agent wrote, otherwise its last message.

Injected into the sandbox container at runtime. Uses only stdlib.
"""

import json
import os
import subprocess
import sys
from typing import Any, Dict, List, Optional

PLAN_MODE = "plan"

LINE_TEXT = "text"
SUBTYPE_SUCCESS = "success"
SUBTYPE_ERROR = "error"

#: How much of opencode's stderr to quote when a run fails.
STDERR_TAIL_CHARS = 2000


def emit(payload: Dict[str, Any]) -> None:
    """Write one NDJSON line to the stream the orchestrator reads."""
    sys.stdout.write(json.dumps(payload) + "\n")
    sys.stdout.flush()


def newest_plan(plans_dir: str) -> Optional[str]:
    """The most recently written plan, if the agent wrote one."""
    try:
        entries = [
            os.path.join(plans_dir, name)
            for name in os.listdir(plans_dir)
            if name.endswith(".md")
        ]
    except OSError:
        return None
    if not entries:
        return None
    newest = max(entries, key=lambda path: os.path.getmtime(path))
    try:
        with open(newest, "r", encoding="utf-8", errors="replace") as handle:
            content = handle.read()
    except OSError:
        return None
    return content if content.strip() else None


def stream_opencode(spec: Dict[str, Any], stderr_path: str) -> tuple:
    """Run opencode, relaying its lines; return (exit code, last text)."""
    argv: List[str] = list(spec["argv"])
    last_text: Optional[str] = None

    with open(spec["task_file"], "r", encoding="utf-8", errors="replace") as task, open(
        stderr_path, "w", encoding="utf-8"
    ) as errors:
        process = subprocess.Popen(
            argv,
            cwd=spec["cwd"],
            stdin=task,
            stdout=subprocess.PIPE,
            stderr=errors,
            text=True,
            bufsize=1,
        )
        assert process.stdout is not None
        for line in process.stdout:
            line = line.rstrip("\n")
            if not line.strip():
                continue
            sys.stdout.write(line + "\n")
            sys.stdout.flush()
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("type") == LINE_TEXT:
                text = (event.get("part") or {}).get("text")
                if text:
                    last_text = text
        return process.wait(), last_text


def read_stderr_tail(stderr_path: str) -> str:
    try:
        with open(stderr_path, "r", encoding="utf-8", errors="replace") as handle:
            return handle.read()[-STDERR_TAIL_CHARS:]
    except OSError:
        return ""


def main() -> int:
    with open(sys.argv[1], "r", encoding="utf-8") as handle:
        spec = json.load(handle)

    stderr_path = f"{spec['task_file']}.stderr"

    emit(
        {
            "type": "system",
            "subtype": "init",
            "cwd": spec["cwd"],
            "tools": spec.get("tools", []),
            "model": spec.get("model", ""),
            "mcp_servers": spec.get("mcp_servers", []),
        }
    )

    try:
        exit_code, last_text = stream_opencode(spec, stderr_path)
    except OSError as exc:
        emit({"type": "result", "subtype": SUBTYPE_ERROR, "error": str(exc)})
        return 1

    if exit_code != 0:
        detail = read_stderr_tail(stderr_path).strip()
        emit(
            {
                "type": "result",
                "subtype": SUBTYPE_ERROR,
                "error": f"opencode exited with code {exit_code}"
                + (f": {detail}" if detail else ""),
            }
        )
        return exit_code

    summary = last_text or ""
    if spec.get("mode") == PLAN_MODE:
        summary = newest_plan(spec.get("plans_dir", "")) or summary

    emit({"type": "result", "subtype": SUBTYPE_SUCCESS, "result": summary})
    return 0


if __name__ == "__main__":
    sys.exit(main())
