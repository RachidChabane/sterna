"""
File System Tools for AI Assistants

Defines tools in OpenAI function calling format that AI assistants can use
to manipulate files in the /workspace sandbox.
"""

from typing import List, Dict, Any

# Tool definitions in OpenAI format
FILE_TOOLS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "List all files and directories in a given path within the /workspace sandbox. Use this to explore the file system structure.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "The directory path to list (relative to /workspace). Use '.' or '/' for root workspace. Examples: '.', 'src', 'src/components'",
                        "default": "."
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read file content from /workspace. For LARGE files (100+ lines), use max_lines or line ranges to save tokens. Use summary_only=true to get file structure without code.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "The file path to read (relative to /workspace). Example: 'src/main.py', 'README.md'"
                    },
                    "max_lines": {
                        "type": "integer",
                        "description": "Maximum lines to return. Reads from start by default. Use with from_end=true for tail."
                    },
                    "from_end": {
                        "type": "boolean",
                        "description": "If true with max_lines, read last N lines instead of first N lines."
                    },
                    "start_line": {
                        "type": "integer",
                        "description": "Start line number (1-indexed). Use with end_line for specific range."
                    },
                    "end_line": {
                        "type": "integer",
                        "description": "End line number (1-indexed, inclusive). Use with start_line for specific range."
                    },
                    "summary_only": {
                        "type": "boolean",
                        "description": "If true, return only file structure (functions, classes, imports) without full code. Great for understanding large files."
                    }
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_code",
            "description": "Search for patterns in files using regex. Faster than reading multiple files. Returns matching lines with file paths and line numbers. Use for: finding function definitions, locating imports, finding all usages of a variable/function, searching for TODOs/FIXMEs.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "Regex pattern to search for. Examples: 'def process_', 'import.*requests', 'TODO|FIXME', 'class.*Controller'"
                    },
                    "path": {
                        "type": "string",
                        "description": "Directory or file to search in (relative to /workspace). Default: '.' (entire workspace). Examples: 'src', 'src/components', 'app.py'",
                        "default": "."
                    },
                    "include": {
                        "type": "string",
                        "description": "Glob pattern to filter files. Examples: '*.py', '*.ts', '*.{js,jsx,ts,tsx}', 'test_*.py'"
                    },
                    "context_lines": {
                        "type": "integer",
                        "description": "Number of lines to show before and after each match (like grep -C). Default: 0",
                        "default": 0
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum number of matches to return. Default: 50",
                        "default": 50
                    },
                    "ignore_case": {
                        "type": "boolean",
                        "description": "Case-insensitive search. Default: false",
                        "default": False
                    }
                },
                "required": ["pattern"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Create a BRAND NEW file in the /workspace sandbox. WARNING: This completely overwrites any existing file! Use this ONLY for creating new files that don't exist yet. For modifying existing files, ALWAYS use edit_file instead.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "The file path to create (relative to /workspace). Example: 'src/new_file.py', 'utils/helper.py'"
                    },
                    "content": {
                        "type": "string",
                        "description": "The complete content for the new file."
                    }
                },
                "required": ["path", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "edit_file",
            "description": "Edit an existing file by replacing specific content. This is the PREFERRED and SAFE way to modify files - it preserves other parts of the file. Perfect for: adding new functions to existing code, fixing bugs, updating specific lines, adding imports, etc. You can make multiple edit_file calls to add different parts to the same file. Example: To add a function, use old_content='# existing code' and new_content='# existing code\\n\\ndef new_function():\\n    pass'",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "The file path to edit (relative to /workspace). Example: 'src/main.py'"
                    },
                    "old_content": {
                        "type": "string",
                        "description": "The exact text segment to find in the file. This should be a distinctive part of the file that appears only once. Include enough context to make it unique (a few lines around the area you want to modify)."
                    },
                    "new_content": {
                        "type": "string",
                        "description": "The replacement text. To ADD content after existing code, include the old_content in new_content followed by your addition. To REMOVE content, make new_content shorter than old_content."
                    }
                },
                "required": ["path", "old_content", "new_content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_directory",
            "description": "Create a new directory in the /workspace sandbox. Parent directories are created automatically if they don't exist.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "The directory path to create (relative to /workspace). Example: 'src/components', 'tests'"
                    }
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "delete_file",
            "description": "Delete a file or directory from the /workspace sandbox. Be careful - this operation cannot be undone. Directories are deleted recursively with all their contents.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "The file or directory path to delete (relative to /workspace). Example: 'old_file.txt', 'unused_folder'"
                    }
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "rename_file",
            "description": "Rename or move a file or directory within the /workspace sandbox. Can be used to reorganize files by moving them to different directories.",
            "parameters": {
                "type": "object",
                "properties": {
                    "old_path": {
                        "type": "string",
                        "description": "The current path of the file/directory (relative to /workspace). Example: 'old_name.py'"
                    },
                    "new_path": {
                        "type": "string",
                        "description": "The new path for the file/directory (relative to /workspace). Example: 'new_name.py' or 'src/new_name.py' to move"
                    }
                },
                "required": ["old_path", "new_path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "run_bash",
            "description": "Execute a bash command in the ISOLATED sandbox. Use for: running tests (npm test, pytest), installing dependencies (npm install, pip install), running build commands, checking versions. IMPORTANT: This sandbox is ISOLATED from GitHub - local git commands (git checkout, git commit, git push) will NOT affect the remote repository. To make changes to GitHub, use the github_* tools instead: github_create_branch to create branches, github_push_files to push changes, github_create_pull_request to create PRs.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The bash command to execute. Examples: 'npm install', 'npm run build', 'npm run test', 'pytest', 'pip install -r requirements.txt'. NOTE: Do NOT use git push/commit/checkout for GitHub operations - use github_* tools instead."
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "Timeout in seconds (default: 120, max: 300). Use higher values for long-running commands like npm install.",
                        "default": 120
                    }
                },
                "required": ["command"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "update_todos",
            "description": "Update the task list to track your progress. Call this at the START of your work to plan tasks, and call it again as you complete each task. The frontend will display this as an interactive checklist.",
            "parameters": {
                "type": "object",
                "properties": {
                    "todos": {
                        "type": "array",
                        "description": "The complete list of tasks. Include all tasks - both completed and pending.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {
                                    "type": "string",
                                    "description": "Unique identifier for the task (e.g., 'task-1', 'task-2')"
                                },
                                "text": {
                                    "type": "string",
                                    "description": "Description of the task"
                                },
                                "status": {
                                    "type": "string",
                                    "enum": ["pending", "in_progress", "completed"],
                                    "description": "Current status: 'pending' (not started), 'in_progress' (currently working on), 'completed' (done)"
                                }
                            },
                            "required": ["id", "text", "status"]
                        }
                    }
                },
                "required": ["todos"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "prepare_pull_request",
            "description": "Prepare pull request metadata as your FINAL STEP after making code changes. This stores the PR title and description so the user can create the PR with one click. IMPORTANT: Before calling this, review recent commits in the repository to understand the naming convention (e.g., 'feat:', 'fix:', conventional commits, etc.). Use run_bash with 'git log --oneline -10' to see recent commits.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "PR title following the repository's commit/PR naming convention. Keep it concise (max 72 chars). Examples: 'feat: add user authentication', 'fix: resolve login redirect issue'"
                    },
                    "summary": {
                        "type": "string",
                        "description": "Brief 1-3 sentence summary of what the PR accomplishes."
                    },
                    "changes": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of key changes made (bullet points). Each item is one change."
                    },
                    "test_plan": {
                        "type": "string",
                        "description": "How the changes can be tested. Include specific steps or commands."
                    }
                },
                "required": ["title", "summary", "changes"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "execute_programming_task",
            "description": "For COMPLEX multi-file programming tasks: refactoring across files, codebase-wide searches/replacements, batch operations, running tests and fixing errors. Generate Python code that performs the task - intermediate results stay in code context (37% token savings). Use relative paths (Path('.')). Print JSON summary at end.",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "Python code for multi-file tasks. Use relative paths like Path('.'). Available: pathlib, subprocess, json, re, os. Print JSON summary at end for results."
                    },
                    "task_description": {
                        "type": "string",
                        "description": "Brief description of what this programming task accomplishes"
                    }
                },
                "required": ["code", "task_description"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "explore_codebase",
            "description": "Use a fast AI model to explore and analyze the codebase structure. Returns relevant files to modify, suggested approach, and code snippets. Use this BEFORE making changes when: (1) you're unfamiliar with the codebase, (2) you need to find where specific functionality lives, (3) the task requires understanding multiple files, or (4) you need to find all places affected by a change. For simple targeted changes where you already know the exact file, skip this and proceed directly.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task": {
                        "type": "string",
                        "description": "Description of what you're trying to accomplish. Be specific about what you need to find or understand in the codebase."
                    },
                    "focus_areas": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional list of directories or file patterns to focus the exploration on (e.g., ['src/', 'tests/', '*.py']). Leave empty to explore the entire workspace."
                    }
                },
                "required": ["task"]
            }
        }
    }
]


def get_file_tools() -> List[Dict[str, Any]]:
    """
    Get the list of file manipulation tools for AI assistants.

    Returns:
        List of tools in OpenAI function calling format
    """
    return FILE_TOOLS


def get_all_tools(include_github: bool = False) -> List[Dict[str, Any]]:
    """
    Get all available tools, optionally including GitHub MCP tools.

    Args:
        include_github: Whether to include GitHub MCP tools

    Returns:
        List of tools in OpenAI function calling format
    """
    tools = FILE_TOOLS.copy()

    if include_github:
        from .mcp_tools import get_github_mcp_tools
        tools.extend(get_github_mcp_tools())

    return tools


def get_tool_by_name(tool_name: str) -> Dict[str, Any] | None:
    """
    Get a specific tool definition by name.

    Args:
        tool_name: Name of the tool (e.g., "read_file")

    Returns:
        Tool definition dict or None if not found
    """
    for tool in FILE_TOOLS:
        if tool["function"]["name"] == tool_name:
            return tool
    return None
