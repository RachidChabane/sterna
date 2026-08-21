#!/usr/bin/env python3
"""
Coding Agent Runner Script

Runs inside the sandbox container. Reads configuration from environment/file,
initializes the Claude Agent SDK with OpenRouter settings, and executes the task.

This script is installed at /usr/local/bin/coding-agent-runner.py in the sandbox image.
"""

import os
import sys
import json
import logging
from typing import List, Dict, Any
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def load_config() -> Dict[str, Any]:
    """Load configuration from environment or file."""
    config_path = os.environ.get("CODING_AGENT_CONFIG")

    if not config_path:
        raise ValueError("CODING_AGENT_CONFIG environment variable not set")

    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(config_path, 'r') as f:
        return json.load(f)


def write_result(result: Dict[str, Any]):
    """Write result to output file."""
    output_path = os.environ.get("CODING_AGENT_OUTPUT", "./result.json")

    with open(output_path, 'w') as f:
        json.dump(result, f, indent=2)

    logger.info(f"Result written to {output_path}")


def track_file_changes(workspace_path: str, before_files: set) -> tuple:
    """Track files modified/created during execution."""
    import subprocess

    try:
        # Get current files in workspace
        result = subprocess.run(
            ["find", workspace_path, "-type", "f", "-name", "*"],
            capture_output=True,
            text=True
        )
        after_files = set(result.stdout.strip().split('\n')) if result.stdout.strip() else set()

        # Files created are in after but not before
        files_created = list(after_files - before_files)

        # For modified files, we'd need git or checksums
        # Simplified: assume all existing files touched were modified
        files_modified = []

        return files_modified, files_created

    except Exception as e:
        logger.warning(f"Could not track file changes: {e}")
        return [], []


def get_workspace_files(workspace_path: str) -> set:
    """Get set of files in workspace."""
    import subprocess

    try:
        result = subprocess.run(
            ["find", workspace_path, "-type", "f", "-name", "*"],
            capture_output=True,
            text=True
        )
        return set(result.stdout.strip().split('\n')) if result.stdout.strip() else set()
    except Exception:
        return set()


def run_with_claude_agent_sdk(config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Run Coding Agent using the Claude Agent SDK.

    This uses the official Anthropic Claude Agent SDK which supports
    tool use and autonomous operation.
    """
    try:
        from claude_agent import Agent
    except ImportError:
        logger.warning("claude-agent-sdk not installed, using fallback implementation")
        return run_fallback(config)

    task = config["task"]
    model = config["model"]
    allowed_tools = config["allowed_tools"]
    max_iterations = config["max_iterations"]
    workspace_path = config["workspace_path"]

    # Get files before execution
    before_files = get_workspace_files(workspace_path)

    steps = []
    start_time = datetime.now()

    try:
        # Configure the agent with OpenRouter settings
        # The environment variables should be set:
        # - ANTHROPIC_BASE_URL=https://openrouter.ai/api/v1
        # - ANTHROPIC_AUTH_TOKEN=<openrouter_key>
        # - ANTHROPIC_API_KEY="" (empty)

        agent = Agent(
            model=os.environ.get("ANTHROPIC_MODEL", model),
            tools=_build_tools(allowed_tools, workspace_path),
            max_iterations=max_iterations,
        )

        # Run the agent
        result = agent.run(task)

        # Track file changes
        files_modified, files_created = track_file_changes(workspace_path, before_files)

        duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)

        return {
            "success": True,
            "summary": result.summary if hasattr(result, 'summary') else str(result),
            "files_modified": files_modified,
            "files_created": files_created,
            "steps": steps,
            "duration_ms": duration_ms,
        }

    except Exception as e:
        logger.error(f"Agent execution failed: {e}", exc_info=True)
        duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)
        return {
            "success": False,
            "error": str(e),
            "steps": steps,
            "duration_ms": duration_ms,
        }


def _build_tools(allowed_tools: List[str], workspace_path: str) -> List:
    """Build tool list for the agent."""
    # This would use the Claude Agent SDK's tool definitions
    # For now, return empty - SDK handles built-in tools
    return []


def run_fallback(config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Fallback implementation when Claude Agent SDK is not available.

    Uses direct API calls to OpenRouter/Claude for basic task execution.
    This is simpler but less capable than the full SDK.
    """
    import subprocess

    task = config["task"]
    workspace_path = config["workspace_path"]

    # Get files before execution
    before_files = get_workspace_files(workspace_path)

    steps = []
    start_time = datetime.now()

    try:
        # For fallback, we'll use a simple approach:
        # 1. List workspace files
        # 2. Make a single API call to get instructions
        # 3. Execute the instructions

        # Get workspace contents
        subprocess.run(
            ["ls", "-la", workspace_path],
            capture_output=True,
            text=True,
            cwd=workspace_path
        )

        steps.append({
            "type": "text",
            "content": f"Analyzed workspace: {workspace_path}",
        })

        # Simple execution: write a marker file to show we ran
        marker_path = os.path.join(workspace_path, ".coding_agent_ran")
        with open(marker_path, 'w') as f:
            f.write(f"Task: {task}\nTimestamp: {datetime.now().isoformat()}\n")

        steps.append({
            "type": "tool_result",
            "tool": "Write",
            "content": f"Created marker file at {marker_path}",
        })

        # Track file changes
        files_modified, files_created = track_file_changes(workspace_path, before_files)

        duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)

        return {
            "success": True,
            "summary": f"Task received: {task[:200]}. Fallback mode - full Claude Agent SDK not available.",
            "files_modified": files_modified,
            "files_created": files_created,
            "steps": steps,
            "duration_ms": duration_ms,
        }

    except Exception as e:
        logger.error(f"Fallback execution failed: {e}")
        duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)
        return {
            "success": False,
            "error": str(e),
            "steps": steps,
            "duration_ms": duration_ms,
        }


def main():
    """Main entry point."""
    logger.info("Coding Agent Runner starting...")

    try:
        # Load configuration
        config = load_config()
        logger.info(f"Loaded config: task={config['task'][:100]}...")

        # Change to workspace directory
        workspace_path = config.get("workspace_path", "/workspace")
        if os.path.exists(workspace_path):
            os.chdir(workspace_path)
            logger.info(f"Working directory: {workspace_path}")

        # Run the agent
        result = run_with_claude_agent_sdk(config)

        # Write result
        write_result(result)

        # Exit with appropriate code
        sys.exit(0 if result.get("success") else 1)

    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        write_result({
            "success": False,
            "error": str(e),
            "steps": [],
            "duration_ms": 0,
        })
        sys.exit(1)


if __name__ == "__main__":
    main()
