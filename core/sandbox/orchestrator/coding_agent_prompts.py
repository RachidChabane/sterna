"""The prompt one coding-agent run is given.

`CodingAgentRunner` writes the whole prompt into the task file the
harness reads on standard input. Assembling it is a pure function of the
job's mode, its task, and the paths the run is confined to, so it lives
here rather than inside the runner's container work.

Every mode shares the same confinement prefix and then says what that
mode is for. A prompt may only name tools the run's harness actually
offers and permits: an instruction to reach for anything else spends
model calls on a refusal and teaches the model that its instructions are
unreliable. The permission profile
(`opencode_harness.build_permission_profile`) is what settles that.
"""

from typing import Optional

from coding_harness import IMPLEMENT_MODE, PLAN_MODE
from opencode_harness import ASK_USER_PERMISSION


#: What a run that may write inside the workspace is told about installing
#: packages. A planning run holds the workspace read-only and is allowed no
#: command that would install anything, so it is not told this.
PACKAGE_INSTALLATION = """Package installation: `pip install <package>` and `npm install` both work.
Do NOT use `npm install -g` (global installs fail on the read-only filesystem).

"""


def build_workspace_instruction(workspace_path: str, plan_path: Optional[str]) -> str:
    """The confinement rules every run is given, whatever its mode.

    A planning run is the one that writes outside the workspace: its
    plan is the single file it is allowed — and required — to put there,
    so every rule that would forbid it names that one exception.
    `plan_path` of None is every other mode, which writes only inside
    the workspace and may install packages there.
    """
    if plan_path:
        scope = ", except for the one file named below"
        outside = f"- Write, create, or modify any file outside {workspace_path} other than {plan_path}"
        absolute = "- Use /tmp/, /home/, /etc/, /root/, or any absolute path outside the workspace other than that one file"
        packages = ""
    else:
        scope = ""
        outside = f"- Write, create, or modify files outside {workspace_path}"
        absolute = "- Use /tmp/, /home/, /etc/, /root/, or any absolute path outside the workspace"
        packages = PACKAGE_INSTALLATION
    return f"""CRITICAL WORKSPACE RESTRICTION:
You are working in the directory: {workspace_path}
ALL file operations MUST be within this directory{scope}. You MUST NOT:
{outside}
{absolute}
- Use relative paths that escape the workspace (like ../)

Use relative paths from the current directory, or paths starting with {workspace_path}/

{packages}You have the `{ASK_USER_PERMISSION}` tool to ask the user questions. Use it when:
- You need clarification that would meaningfully change your approach
- You're choosing between multiple valid strategies and user preference matters
- The task is ambiguous and guessing wrong would waste significant effort

Do NOT use it for:
- Routine confirmations ("Should I proceed?", "Is this OK?")
- Questions you can answer with your own judgment
- Permission to perform operations the user already requested

---
"""


def build_planning_prompt(task: str, plan_path: str) -> str:
    """The prompt for planning mode.

    A planning run explores the workspace, which is read-only for its
    whole duration, and delivers an implementation plan rather than
    changes. The plan is a file it writes outside the workspace:
    `opencode_run_wrapper` reads the plans directory when the run ends
    and reports what it finds there as the run's result, so a run that
    writes nothing there has produced nothing.
    """
    return f"""You are a planning agent. Your goal is to deeply explore the codebase and produce a thorough implementation plan.

## Task
{task}

## Exploration Strategy
- Use `read` to open files, and `glob` and `grep` to find them.
- Use `bash` for read-only commands like `find`, `wc -l`, `git log`, `tree` to understand the project structure.
- Explore thoroughly before writing the plan — the more you understand, the better the plan.

## Rules
- Do NOT modify, create, edit, or delete any file in the workspace. This is PLANNING ONLY, the workspace is read-only, and every such attempt fails.
- Do NOT implement any changes — only produce a plan.
- When done exploring, use `write` to save your plan to {plan_path}. That file is the only output that is delivered; nothing else you write or say is.

## Plan Format
Your plan MUST use this exact markdown structure:

# Implementation Plan: <clear title>

## Summary
<2-3 sentence summary of what will be implemented>

## Files to Modify
- path/to/file1.py - <what changes>
- path/to/file2.ts - <what changes>

### Step 1: <step title>
<detailed description of what to do>
**Files:** file1.py, file2.py

### Step 2: <step title>
<detailed description of what to do>
**Files:** file3.py

(continue for all steps)

## Testing Plan
<how to verify the implementation works>
"""


def build_implementation_prompt(task: str, plan_content: str) -> str:
    """The prompt for implementation mode.

    The approved plan travels in the prompt itself, so the run works
    from what it was given rather than from a file it would have to find.
    """
    return f"""MODE: IMPLEMENTATION

Follow the approved plan step by step.

## Task
{task}

## Plan
{plan_content}
"""


def build_task_prompt(
    *,
    mode: str,
    task: str,
    plan_content: Optional[str],
    workspace_path: str,
    plan_path: str,
) -> str:
    """The whole prompt one run is given, on standard input."""
    planning = mode == PLAN_MODE
    prefix = build_workspace_instruction(
        workspace_path, plan_path if planning else None
    )
    if planning:
        return prefix + build_planning_prompt(task, plan_path)
    if mode == IMPLEMENT_MODE and plan_content:
        return prefix + build_implementation_prompt(task, plan_content)
    return prefix + "TASK:\n" + task
