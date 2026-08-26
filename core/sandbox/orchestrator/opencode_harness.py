"""Build the opencode invocation for one coding-agent job.

Everything here is a pure function of the job's parameters, so the
permission profile, the environment, and the command line are all
testable without a container.

Three properties of ``opencode run`` shape what is built:

Configuration arrives through the environment, never the workspace.
    opencode reads ``opencode.json`` / ``opencode.jsonc`` from the
    working directory and every directory above it, plus
    ``.opencode/``. ``OPENCODE_CONFIG_CONTENT`` is merged last and so
    wins, and ``OPENCODE_DISABLE_PROJECT_CONFIG`` moves instruction
    discovery (``AGENTS.md``, ``CLAUDE.md``, ``CONTEXT.md``) off the
    workspace onto the ephemeral config directory. Keys the injected
    config does not set can still be contributed by a file planted in
    the workspace, so `CodingAgentRunner` refuses to start a job when
    one is present; these two variables narrow what such a file could
    reach, they do not replace that check.

The task arrives on standard input.
    ``opencode run`` reads stdin to EOF whenever stdin is not a
    terminal and merges it into the prompt, so a job whose stdin stays
    open never starts. The task file is stdin and the message argument
    is empty, the same shape the Claude harness uses.

A session title costs a model call unless one is supplied.
    ``--title`` skips the title-generation turn, which would otherwise
    bill a model call against the job that no step ever reports.
"""

import json
from typing import Any, Dict, List, Optional, Tuple

import yaml

from opencode_output_adapter import opencode_tool_name

PLAN_MODE = "plan"

PLAN_AGENT = "plan"
BUILD_AGENT = "build"

#: MCP server name for the ask-user relay. opencode exposes a server's
#: tools as ``{server}_{tool}``, so this becomes ``ask-user_ask_user``.
ASK_USER_SERVER = "ask-user"
ASK_USER_TOOL = "ask_user"
ASK_USER_PERMISSION = f"{ASK_USER_SERVER}_{ASK_USER_TOOL}"

#: Session title, supplied to skip opencode's title-generation call.
SESSION_TITLE = "sterna-coding-agent"

#: OpenRouter's OpenAI-compatible endpoint, which opencode's provider
#: adapter speaks natively.
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
API_KEY_ENV_VAR = "OPENROUTER_API_KEY"

ALLOW = "allow"
DENY = "deny"
WILDCARD = "*"

# Exploration commands a planning run may shell out to. Mirrors the
# read-only command set the Claude harness allows in plan mode.
PLAN_BASH_ALLOWED = (
    "ls*", "cat*", "grep*", "find*", "head*", "tail*", "wc*", "sort*",
    "uniq*", "diff*", "echo*", "tree*", "git*", "file*",
)

# Commands denied in every mode: they reach the network or the host
# outside the paths the sandbox accounts for.
BASH_DENIED = (
    "sudo*", "su *", "curl*", "wget*", "ssh*", "scp*", "nc*", "netcat*",
)


#: Marks an agent as one the primary agent may delegate to.
SUBAGENT_MODE = "subagent"

#: Frontmatter delimiter in an agent definition.
FRONTMATTER_FENCE = "---"

#: Keys an imported sub-agent carries, in the vocabulary it was written in.
IMPORTED_DESCRIPTION_KEY = "description"
IMPORTED_ALLOWED_TOOLS_KEY = "tools"
IMPORTED_DENIED_TOOLS_KEY = "disallowedTools"


def agent_for_mode(mode: str) -> str:
    """opencode's built-in agent that matches a Sterna mode."""
    return PLAN_AGENT if mode == PLAN_MODE else BUILD_AGENT


def config_home_for(ephemeral_home: str) -> str:
    """The job's own configuration directory."""
    return f"{ephemeral_home}/.config"


def subagent_dir_for(ephemeral_home: str) -> str:
    """Where opencode looks for this job's sub-agent definitions.

    Agents are discovered under the configuration directory that
    ``XDG_CONFIG_HOME`` names, and under the workspace's own
    ``.opencode/``. ``build_env`` sets ``OPENCODE_DISABLE_PROJECT_CONFIG``,
    which takes the workspace out of that search, so this directory is
    the only one a job's sub-agents can be planted in.
    """
    return f"{config_home_for(ephemeral_home)}/opencode/agent"


def _split_frontmatter(markdown: str) -> Tuple[Dict[str, Any], str]:
    """The YAML frontmatter and the body of one agent definition."""
    parts = markdown.split(FRONTMATTER_FENCE, 2)
    if len(parts) < 3:
        return {}, markdown.strip()
    try:
        frontmatter = yaml.safe_load(parts[1])
    except yaml.YAMLError:
        frontmatter = None
    return (frontmatter if isinstance(frontmatter, dict) else {}), parts[2].strip()


def _opencode_tools(names: Any) -> List[str]:
    """The opencode tools a list of payload tool names refers to."""
    if not isinstance(names, list):
        return []
    resolved = (opencode_tool_name(str(name)) for name in names)
    return [name for name in resolved if name]


def _subagent_permission(frontmatter: Dict[str, Any]) -> Dict[str, str]:
    """One sub-agent's tool restrictions as opencode permission rules.

    An imported sub-agent names an allowlist, a denylist, or neither. An
    allowlist is closed with a wildcard denial so the tools it leaves
    out stay out; a denial is applied last so a tool named on both lists
    is denied.
    """
    permission: Dict[str, str] = {}
    allowed = _opencode_tools(frontmatter.get(IMPORTED_ALLOWED_TOOLS_KEY))
    if allowed:
        permission[WILDCARD] = DENY
        permission.update({name: ALLOW for name in allowed})
    permission.update(
        {name: DENY for name in _opencode_tools(frontmatter.get(IMPORTED_DENIED_TOOLS_KEY))}
    )
    return permission


def build_subagent_definition(source_markdown: str) -> str:
    """Rewrite one imported sub-agent as an opencode agent definition.

    A sub-agent is imported in the vocabulary of the CLI it was written
    for, which opencode does not share: it names its allowed tools as a
    list, where opencode's agent schema accepts only an object, and
    opencode rejects the whole configuration — failing the run, not just
    the one agent — over the mismatch. It also names its model as a bare
    alias, which is not a ``provider/model`` reference opencode can
    resolve, and would in any case take the sub-agent off the model the
    job was quoted and billed for; dropping it leaves the sub-agent on
    the job's own model.

    What survives the rewrite is the sub-agent's purpose: its
    description, its system prompt, and its tool restrictions, the last
    expressed as the permission rules opencode enforces. The agent's
    name is not part of the definition — opencode takes it from the
    file name.
    """
    frontmatter, body = _split_frontmatter(source_markdown)

    definition: Dict[str, Any] = {}
    description = str(frontmatter.get(IMPORTED_DESCRIPTION_KEY) or "").strip()
    if description:
        definition[IMPORTED_DESCRIPTION_KEY] = description
    definition["mode"] = SUBAGENT_MODE
    permission = _subagent_permission(frontmatter)
    if permission:
        definition["permission"] = permission

    header = yaml.safe_dump(definition, default_flow_style=False, sort_keys=False).strip()
    return f"{FRONTMATTER_FENCE}\n{header}\n{FRONTMATTER_FENCE}\n\n{body}\n"


def plans_dir_for(ephemeral_home: str) -> str:
    """Where the planning agent is allowed to write its plan.

    opencode's plan agent may write under its data directory's
    ``plans/``; the workspace copy it would otherwise prefer is
    unwritable while a planning run holds the workspace read-only.
    """
    return f"{ephemeral_home}/.local/share/opencode/plans"


def build_permission_profile(mode: str, plans_dir: str) -> Dict[str, Any]:
    """The tool permissions for one mode.

    Planning runs may read and explore but not write; implementing runs
    may write inside the workspace. Both may ask the user a question,
    and neither may reach the network from a tool.

    opencode's ``bash`` tool can still write files a permission rule
    denies to ``edit``, so a planning run's real write barrier is the
    read-only workspace the runner imposes at the filesystem level.
    This profile denies the commands that would try.
    """
    if mode == PLAN_MODE:
        bash: Dict[str, str] = {WILDCARD: DENY}
        bash.update({pattern: ALLOW for pattern in PLAN_BASH_ALLOWED})
        return {
            "read": ALLOW,
            "glob": ALLOW,
            "grep": ALLOW,
            "list": ALLOW,
            # `edit` is deliberately absent. opencode's own plan agent
            # already denies it everywhere but its plans directories,
            # and its patterns are matched relative to the worktree; a
            # rule added here is merged after those and would override
            # them, leaving the agent unable to record its plan.
            "task": DENY,
            "webfetch": DENY,
            "websearch": DENY,
            "bash": bash,
            "question": ALLOW,
            ASK_USER_PERMISSION: ALLOW,
            "external_directory": {WILDCARD: DENY, f"{plans_dir}/*": ALLOW},
        }

    permissive_bash: Dict[str, str] = {WILDCARD: ALLOW}
    permissive_bash.update({pattern: DENY for pattern in BASH_DENIED})
    return {
        "read": ALLOW,
        "glob": ALLOW,
        "grep": ALLOW,
        "list": ALLOW,
        "edit": ALLOW,
        "webfetch": DENY,
        "websearch": DENY,
        "bash": permissive_bash,
        "question": ALLOW,
        ASK_USER_PERMISSION: ALLOW,
    }


def build_config(
    *,
    mode: str,
    model: str,
    ephemeral_home: str,
    max_steps: int,
    base_url: str = OPENROUTER_BASE_URL,
    api_key_env_var: str = API_KEY_ENV_VAR,
    ask_user_command: Optional[List[str]] = None,
    ask_user_environment: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """The opencode configuration injected through the environment."""
    plans_dir = plans_dir_for(ephemeral_home)
    provider_id, _, model_id = model.partition("/")
    config: Dict[str, Any] = {
        "$schema": "https://opencode.ai/config.json",
        "model": f"openrouter/{model}",
        "share": "disabled",
        "autoupdate": False,
        "provider": {
            "openrouter": {
                "options": {
                    "baseURL": base_url,
                    "apiKey": "{env:" + api_key_env_var + "}",
                },
                "models": {model: {"name": model_id or provider_id}},
            }
        },
        "agent": {
            agent_for_mode(mode): {
                "permission": build_permission_profile(mode, plans_dir),
                "steps": max_steps,
            }
        },
    }
    if ask_user_command:
        config["mcp"] = {
            ASK_USER_SERVER: {
                "type": "local",
                "command": list(ask_user_command),
                "environment": dict(ask_user_environment or {}),
                "enabled": True,
            }
        }
    return config


def build_env(
    *,
    config: Dict[str, Any],
    ephemeral_home: str,
    api_key: str,
    base_env: Dict[str, str],
    api_key_env_var: str = API_KEY_ENV_VAR,
) -> Dict[str, str]:
    """The environment one opencode run is given.

    ``base_env`` carries the sandbox-wide settings (proxy, TLS trust,
    package install paths) the runner applies to every harness; the
    entries added here are what opencode itself reads.
    """
    env = dict(base_env)
    env.update(
        {
            api_key_env_var: api_key,
            "HOME": ephemeral_home,
            "XDG_CONFIG_HOME": config_home_for(ephemeral_home),
            "XDG_DATA_HOME": f"{ephemeral_home}/.local/share",
            "XDG_CACHE_HOME": f"{ephemeral_home}/.cache",
            "XDG_STATE_HOME": f"{ephemeral_home}/.local/state",
            # Merged last, so it outranks any config file the workspace
            # or a directory above it happens to hold.
            "OPENCODE_CONFIG_CONTENT": json.dumps(config),
            # Read instructions from the ephemeral config directory
            # rather than the workspace.
            "OPENCODE_DISABLE_PROJECT_CONFIG": "1",
            "OPENCODE_DISABLE_CLAUDE_CODE_PROMPT": "1",
            # Every remaining setting closes a path out of the sandbox:
            # no plugin download, no model catalogue fetch, no upgrade
            # check, no session sharing, no language-server download.
            "OPENCODE_PURE": "1",
            "OPENCODE_DISABLE_DEFAULT_PLUGINS": "1",
            "OPENCODE_DISABLE_MODELS_FETCH": "1",
            "OPENCODE_DISABLE_AUTOUPDATE": "1",
            "OPENCODE_DISABLE_SHARE": "1",
            "OPENCODE_DISABLE_LSP_DOWNLOAD": "1",
        }
    )
    return env


def build_argv(mode: str) -> List[str]:
    """The opencode command line, with the message left to stdin.

    The step ceiling is not a flag; it rides in the agent's
    configuration, which `build_config` sets.
    """
    return [
        "opencode",
        "run",
        "--format",
        "json",
        "--agent",
        agent_for_mode(mode),
        "--title",
        SESSION_TITLE,
    ]


def build_wrapper_spec(
    *,
    mode: str,
    workspace_path: str,
    ephemeral_home: str,
    task_file: str,
    model: str,
    tools: List[str],
) -> Dict[str, Any]:
    """The job description the in-sandbox wrapper reads."""
    return {
        "argv": build_argv(mode),
        "cwd": workspace_path,
        "task_file": task_file,
        "mode": mode,
        "model": model,
        "tools": tools,
        "plans_dir": plans_dir_for(ephemeral_home),
        "mcp_servers": [ASK_USER_SERVER],
    }
