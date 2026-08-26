"""Tool permissions written into the Claude Code harness's settings file.

`CodingAgentRunner` writes these into ``$HOME/.claude/settings.json``
inside the job's ephemeral home. They express intent: the Claude Code
CLI does not enforce deny rules against its own built-in tools, so a
planning run's actual write barrier is the read-only workspace the
runner imposes at the filesystem level.
"""

from typing import Any, Dict, List

PLAN_MODE = "plan"

# Exploration commands a planning run may shell out to.
PLAN_BASH_ALLOWED = (
    "Bash(ls*)", "Bash(cat*)", "Bash(grep*)", "Bash(find*)", "Bash(head*)",
    "Bash(tail*)", "Bash(wc*)", "Bash(sort*)", "Bash(uniq*)", "Bash(diff*)",
    "Bash(echo*)", "Bash(tree*)", "Bash(git*)", "Bash(file*)",
)

# Commands a planning run must not reach: they mutate the workspace or
# leave the sandbox.
PLAN_BASH_DENIED = (
    "Bash(sudo*)", "Bash(rm*)", "Bash(mv*)", "Bash(cp*)", "Bash(chmod*)",
    "Bash(python*)", "Bash(node*)", "Bash(npm*)", "Bash(pip*)",
    "Bash(curl*)", "Bash(wget*)", "Bash(ssh*)",
)

# Commands an implementing run may use: the sandbox itself bounds them.
IMPLEMENT_BASH_ALLOWED = (
    "Bash(ls*)", "Bash(cat*)", "Bash(grep*)", "Bash(find*)", "Bash(head*)",
    "Bash(tail*)", "Bash(wc*)", "Bash(sort*)", "Bash(uniq*)", "Bash(diff*)",
    "Bash(echo*)", "Bash(printf*)", "Bash(mkdir*)", "Bash(touch*)",
    "Bash(rm*)", "Bash(cp*)", "Bash(mv*)", "Bash(chmod*)", "Bash(python*)",
    "Bash(node*)", "Bash(npm*)", "Bash(npx*)", "Bash(pip*)", "Bash(git*)",
)

# Commands denied in every mode: they reach the network or the host.
IMPLEMENT_BASH_DENIED = (
    "Bash(sudo*)", "Bash(su*)", "Bash(curl*)", "Bash(wget*)", "Bash(ssh*)",
    "Bash(scp*)", "Bash(nc*)", "Bash(netcat*)",
)

SYSTEM_DIRECTORIES = ("/etc/**", "/root/**")


def _system_denies(actions: List[str]) -> List[str]:
    return [
        f"{action}({directory})"
        for directory in SYSTEM_DIRECTORIES
        for action in actions
    ]


def settings_for(mode: str, workspace_path: str, ephemeral_home: str) -> Dict[str, Any]:
    """The settings document for one mode.

    A planning run may read the whole workspace but write only inside
    its ephemeral home, where the plan lands. An implementing run may
    also write within the workspace.
    """
    home_access = [f"Read({ephemeral_home}/**)", f"Write({ephemeral_home}/**)"]
    enter_workspace = f"Bash(cd {workspace_path}*)"

    if mode == PLAN_MODE:
        allow = [f"Read({workspace_path}/**)", *home_access, enter_workspace]
        allow.extend(PLAN_BASH_ALLOWED)
        deny = [f"Write({workspace_path}/**)", f"Edit({workspace_path}/**)"]
        deny.extend(_system_denies(["Read"]))
        deny.extend(PLAN_BASH_DENIED)
    else:
        allow = [
            f"Read({workspace_path}/**)",
            f"Write({workspace_path}/**)",
            f"Edit({workspace_path}/**)",
            *home_access,
            enter_workspace,
        ]
        allow.extend(IMPLEMENT_BASH_ALLOWED)
        deny = _system_denies(["Read", "Write", "Edit"])
        deny.extend(IMPLEMENT_BASH_DENIED)

    return {"permissions": {"allow": allow, "deny": deny}}
