"""
MCP Tools Integration for Orchestrator

Provides MCP server management and tool execution for sandboxed code sessions.
Uses the existing MCP sandbox infrastructure to run GitHub, Notion, etc. MCP servers.
"""

import logging
from typing import Dict, List, Any, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class MCPToolDefinition:
    """Definition of an MCP tool for LLM consumption."""
    name: str
    description: str
    input_schema: Dict[str, Any]
    mcp_server: str  # e.g., 'github', 'notion'


# GitHub MCP Server Tool Definitions
# Based on @modelcontextprotocol/server-github
GITHUB_MCP_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "github_get_issue",
            "description": "Get details of a specific GitHub issue by number. Returns issue title, body, state, labels, assignees, and comments.",
            "parameters": {
                "type": "object",
                "properties": {
                    "owner": {
                        "type": "string",
                        "description": "Repository owner (username or organization)"
                    },
                    "repo": {
                        "type": "string",
                        "description": "Repository name"
                    },
                    "issue_number": {
                        "type": "integer",
                        "description": "Issue number"
                    }
                },
                "required": ["owner", "repo", "issue_number"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "github_list_issues",
            "description": "List issues in a GitHub repository. Can filter by state (open, closed, all), labels, assignee, etc.",
            "parameters": {
                "type": "object",
                "properties": {
                    "owner": {
                        "type": "string",
                        "description": "Repository owner (username or organization)"
                    },
                    "repo": {
                        "type": "string",
                        "description": "Repository name"
                    },
                    "state": {
                        "type": "string",
                        "enum": ["open", "closed", "all"],
                        "default": "open",
                        "description": "Filter by issue state"
                    },
                    "labels": {
                        "type": "string",
                        "description": "Comma-separated list of label names"
                    },
                    "per_page": {
                        "type": "integer",
                        "default": 30,
                        "description": "Number of issues per page (max 100)"
                    }
                },
                "required": ["owner", "repo"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "github_create_issue",
            "description": "Create a new issue in a GitHub repository.",
            "parameters": {
                "type": "object",
                "properties": {
                    "owner": {
                        "type": "string",
                        "description": "Repository owner (username or organization)"
                    },
                    "repo": {
                        "type": "string",
                        "description": "Repository name"
                    },
                    "title": {
                        "type": "string",
                        "description": "Issue title"
                    },
                    "body": {
                        "type": "string",
                        "description": "Issue body/description (supports Markdown)"
                    },
                    "labels": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Labels to add to the issue"
                    },
                    "assignees": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Usernames to assign to the issue"
                    }
                },
                "required": ["owner", "repo", "title"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "github_create_pull_request",
            "description": "Create a pull request on GitHub. IMPORTANT: The 'head' branch MUST exist on GitHub with commits (use github_create_branch and github_push_files first). The 'head' branch must have commits that differ from 'base' branch, otherwise GitHub will return a 422 error.",
            "parameters": {
                "type": "object",
                "properties": {
                    "owner": {
                        "type": "string",
                        "description": "Repository owner (username or organization)"
                    },
                    "repo": {
                        "type": "string",
                        "description": "Repository name"
                    },
                    "title": {
                        "type": "string",
                        "description": "Pull request title"
                    },
                    "body": {
                        "type": "string",
                        "description": "Pull request body/description (supports Markdown)"
                    },
                    "head": {
                        "type": "string",
                        "description": "The branch containing your changes (e.g., 'feature-branch')"
                    },
                    "base": {
                        "type": "string",
                        "description": "The branch you want to merge into (e.g., 'main')"
                    },
                    "draft": {
                        "type": "boolean",
                        "default": False,
                        "description": "Create as draft PR"
                    }
                },
                "required": ["owner", "repo", "title", "head", "base"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "github_get_pull_request",
            "description": "Get details of a specific pull request by number.",
            "parameters": {
                "type": "object",
                "properties": {
                    "owner": {
                        "type": "string",
                        "description": "Repository owner"
                    },
                    "repo": {
                        "type": "string",
                        "description": "Repository name"
                    },
                    "pull_number": {
                        "type": "integer",
                        "description": "Pull request number"
                    }
                },
                "required": ["owner", "repo", "pull_number"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "github_list_pull_requests",
            "description": "List pull requests in a repository.",
            "parameters": {
                "type": "object",
                "properties": {
                    "owner": {
                        "type": "string",
                        "description": "Repository owner"
                    },
                    "repo": {
                        "type": "string",
                        "description": "Repository name"
                    },
                    "state": {
                        "type": "string",
                        "enum": ["open", "closed", "all"],
                        "default": "open"
                    },
                    "per_page": {
                        "type": "integer",
                        "default": 30
                    }
                },
                "required": ["owner", "repo"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "github_get_file_contents",
            "description": "Get the contents of a file from a GitHub repository.",
            "parameters": {
                "type": "object",
                "properties": {
                    "owner": {
                        "type": "string",
                        "description": "Repository owner"
                    },
                    "repo": {
                        "type": "string",
                        "description": "Repository name"
                    },
                    "path": {
                        "type": "string",
                        "description": "Path to the file in the repository"
                    },
                    "ref": {
                        "type": "string",
                        "description": "Git ref (branch, tag, or commit SHA). Defaults to default branch."
                    }
                },
                "required": ["owner", "repo", "path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "github_push_files",
            "description": "Push file changes DIRECTLY to GitHub. Creates or updates files in a single commit. Use this INSTEAD of local git add/commit/push. After editing files in the sandbox, use this tool to push the changes to a GitHub branch. Workflow: 1) github_create_branch, 2) edit files locally, 3) github_push_files to push, 4) github_create_pull_request.",
            "parameters": {
                "type": "object",
                "properties": {
                    "owner": {
                        "type": "string",
                        "description": "Repository owner"
                    },
                    "repo": {
                        "type": "string",
                        "description": "Repository name"
                    },
                    "branch": {
                        "type": "string",
                        "description": "Branch to push to"
                    },
                    "message": {
                        "type": "string",
                        "description": "Commit message"
                    },
                    "files": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "path": {"type": "string"},
                                "content": {"type": "string"}
                            },
                            "required": ["path", "content"]
                        },
                        "description": "List of files to push with their paths and contents"
                    }
                },
                "required": ["owner", "repo", "branch", "message", "files"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "github_create_branch",
            "description": "Create a new branch DIRECTLY on GitHub. Use this INSTEAD of local git checkout/branch commands. This creates the branch on the remote repository so you can then use github_push_files to add commits and github_create_pull_request to open a PR.",
            "parameters": {
                "type": "object",
                "properties": {
                    "owner": {
                        "type": "string",
                        "description": "Repository owner"
                    },
                    "repo": {
                        "type": "string",
                        "description": "Repository name"
                    },
                    "branch": {
                        "type": "string",
                        "description": "Name of the new branch"
                    },
                    "from_branch": {
                        "type": "string",
                        "description": "Source branch to create from (defaults to default branch)"
                    }
                },
                "required": ["owner", "repo", "branch"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "github_search_code",
            "description": "Search for code across GitHub repositories.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query (see GitHub code search syntax)"
                    },
                    "per_page": {
                        "type": "integer",
                        "default": 30,
                        "description": "Results per page"
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "github_search_issues",
            "description": "Search for issues and pull requests across GitHub.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query (see GitHub issues search syntax)"
                    },
                    "per_page": {
                        "type": "integer",
                        "default": 30
                    }
                },
                "required": ["query"]
            }
        }
    }
]


def get_github_mcp_tools() -> List[Dict[str, Any]]:
    """
    Get GitHub MCP tool definitions in OpenAI function calling format.

    Returns:
        List of tool definitions for the LLM
    """
    return GITHUB_MCP_TOOLS


def get_all_mcp_tools(enabled_connectors: List[str] = None) -> List[Dict[str, Any]]:
    """
    Get all available MCP tools based on enabled connectors.

    Args:
        enabled_connectors: List of enabled connector slugs (e.g., ['github', 'notion'])

    Returns:
        List of tool definitions
    """
    enabled_connectors = enabled_connectors or []
    tools = []

    if 'github' in enabled_connectors:
        tools.extend(GITHUB_MCP_TOOLS)

    # Add other connectors as they're implemented
    # if 'notion' in enabled_connectors:
    #     tools.extend(NOTION_MCP_TOOLS)

    return tools


class MCPToolExecutor:
    """
    Executes MCP tools by calling the appropriate APIs.

    For GitHub tools, uses the GitHub API directly with the user's OAuth token.
    This is more efficient than spawning MCP containers for each tool call.
    """

    def __init__(self, github_token: Optional[str] = None):
        """
        Initialize MCP tool executor.

        Args:
            github_token: GitHub OAuth access token
        """
        self.github_token = github_token
        self._session = None

    @property
    def session(self):
        """Lazy-initialized HTTP session."""
        if self._session is None:
            import httpx
            self._session = httpx.Client(timeout=30.0)
        return self._session

    def execute(
        self,
        tool_name: str,
        arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Execute an MCP tool.

        Args:
            tool_name: Name of the tool to execute
            arguments: Tool arguments

        Returns:
            Tool execution result
        """
        logger.info(f"Executing MCP tool: {tool_name}")

        # Route to appropriate handler
        if tool_name.startswith('github_'):
            return self._execute_github_tool(tool_name, arguments)
        else:
            return {
                "success": False,
                "error": f"Unknown MCP tool: {tool_name}"
            }

    def _execute_github_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute a GitHub API tool."""
        if not self.github_token:
            return {
                "success": False,
                "error": "GitHub token not configured. Please connect your GitHub account."
            }

        headers = {
            "Authorization": f"Bearer {self.github_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28"
        }

        try:
            # Route to specific GitHub API handlers
            handlers = {
                "github_get_issue": self._github_get_issue,
                "github_list_issues": self._github_list_issues,
                "github_create_issue": self._github_create_issue,
                "github_create_pull_request": self._github_create_pull_request,
                "github_get_pull_request": self._github_get_pull_request,
                "github_list_pull_requests": self._github_list_pull_requests,
                "github_get_file_contents": self._github_get_file_contents,
                "github_push_files": self._github_push_files,
                "github_create_branch": self._github_create_branch,
                "github_search_code": self._github_search_code,
                "github_search_issues": self._github_search_issues,
            }

            handler = handlers.get(tool_name)
            if not handler:
                return {
                    "success": False,
                    "error": f"Unknown GitHub tool: {tool_name}"
                }

            return handler(arguments, headers)

        except Exception as e:
            logger.error(f"GitHub API error: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    def _github_get_issue(self, args: Dict, headers: Dict) -> Dict:
        """Get a GitHub issue."""
        url = f"https://api.github.com/repos/{args['owner']}/{args['repo']}/issues/{args['issue_number']}"
        response = self.session.get(url, headers=headers)
        response.raise_for_status()
        return {"success": True, "data": response.json()}

    def _github_list_issues(self, args: Dict, headers: Dict) -> Dict:
        """List GitHub issues."""
        url = f"https://api.github.com/repos/{args['owner']}/{args['repo']}/issues"
        params = {
            "state": args.get("state", "open"),
            "per_page": args.get("per_page", 30)
        }
        if args.get("labels"):
            params["labels"] = args["labels"]

        response = self.session.get(url, headers=headers, params=params)
        response.raise_for_status()
        return {"success": True, "data": response.json()}

    def _github_create_issue(self, args: Dict, headers: Dict) -> Dict:
        """Create a GitHub issue."""
        url = f"https://api.github.com/repos/{args['owner']}/{args['repo']}/issues"
        data = {
            "title": args["title"],
            "body": args.get("body", ""),
        }
        if args.get("labels"):
            data["labels"] = args["labels"]
        if args.get("assignees"):
            data["assignees"] = args["assignees"]

        response = self.session.post(url, headers=headers, json=data)
        response.raise_for_status()
        return {"success": True, "data": response.json()}

    def _github_create_pull_request(self, args: Dict, headers: Dict) -> Dict:
        """Create a GitHub pull request."""
        url = f"https://api.github.com/repos/{args['owner']}/{args['repo']}/pulls"
        data = {
            "title": args["title"],
            "body": args.get("body", ""),
            "head": args["head"],
            "base": args["base"],
            "draft": args.get("draft", False)
        }

        response = self.session.post(url, headers=headers, json=data)
        response.raise_for_status()
        return {"success": True, "data": response.json()}

    def _github_get_pull_request(self, args: Dict, headers: Dict) -> Dict:
        """Get a GitHub pull request."""
        url = f"https://api.github.com/repos/{args['owner']}/{args['repo']}/pulls/{args['pull_number']}"
        response = self.session.get(url, headers=headers)
        response.raise_for_status()
        return {"success": True, "data": response.json()}

    def _github_list_pull_requests(self, args: Dict, headers: Dict) -> Dict:
        """List GitHub pull requests."""
        url = f"https://api.github.com/repos/{args['owner']}/{args['repo']}/pulls"
        params = {
            "state": args.get("state", "open"),
            "per_page": args.get("per_page", 30)
        }

        response = self.session.get(url, headers=headers, params=params)
        response.raise_for_status()
        return {"success": True, "data": response.json()}

    def _github_get_file_contents(self, args: Dict, headers: Dict) -> Dict:
        """Get file contents from GitHub."""
        url = f"https://api.github.com/repos/{args['owner']}/{args['repo']}/contents/{args['path']}"
        params = {}
        if args.get("ref"):
            params["ref"] = args["ref"]

        response = self.session.get(url, headers=headers, params=params)
        response.raise_for_status()
        data = response.json()

        # Decode base64 content if present
        if data.get("content") and data.get("encoding") == "base64":
            import base64
            data["decoded_content"] = base64.b64decode(data["content"]).decode("utf-8")

        return {"success": True, "data": data}

    def _github_push_files(self, args: Dict, headers: Dict) -> Dict:
        """Push files to GitHub repository."""
        owner = args["owner"]
        repo = args["repo"]
        branch = args["branch"]
        message = args["message"]
        files = args["files"]

        # Get the latest commit SHA for the branch
        ref_url = f"https://api.github.com/repos/{owner}/{repo}/git/refs/heads/{branch}"
        ref_response = self.session.get(ref_url, headers=headers)
        ref_response.raise_for_status()
        latest_commit_sha = ref_response.json()["object"]["sha"]

        # Get the tree SHA for the latest commit
        commit_url = f"https://api.github.com/repos/{owner}/{repo}/git/commits/{latest_commit_sha}"
        commit_response = self.session.get(commit_url, headers=headers)
        commit_response.raise_for_status()
        base_tree_sha = commit_response.json()["tree"]["sha"]

        # Create blobs for each file
        tree_items = []
        for file in files:
            blob_url = f"https://api.github.com/repos/{owner}/{repo}/git/blobs"
            blob_response = self.session.post(blob_url, headers=headers, json={
                "content": file["content"],
                "encoding": "utf-8"
            })
            blob_response.raise_for_status()
            blob_sha = blob_response.json()["sha"]

            tree_items.append({
                "path": file["path"],
                "mode": "100644",
                "type": "blob",
                "sha": blob_sha
            })

        # Create new tree
        tree_url = f"https://api.github.com/repos/{owner}/{repo}/git/trees"
        tree_response = self.session.post(tree_url, headers=headers, json={
            "base_tree": base_tree_sha,
            "tree": tree_items
        })
        tree_response.raise_for_status()
        new_tree_sha = tree_response.json()["sha"]

        # Create new commit
        new_commit_url = f"https://api.github.com/repos/{owner}/{repo}/git/commits"
        new_commit_response = self.session.post(new_commit_url, headers=headers, json={
            "message": message,
            "tree": new_tree_sha,
            "parents": [latest_commit_sha]
        })
        new_commit_response.raise_for_status()
        new_commit_sha = new_commit_response.json()["sha"]

        # Update branch reference
        update_ref_response = self.session.patch(ref_url, headers=headers, json={
            "sha": new_commit_sha
        })
        update_ref_response.raise_for_status()

        return {
            "success": True,
            "data": {
                "commit_sha": new_commit_sha,
                "files_pushed": [f["path"] for f in files],
                "branch": branch
            }
        }

    def _github_create_branch(self, args: Dict, headers: Dict) -> Dict:
        """Create a new branch in GitHub repository."""
        owner = args["owner"]
        repo = args["repo"]
        new_branch = args["branch"]
        from_branch = args.get("from_branch", "main")

        # Get the SHA of the source branch
        ref_url = f"https://api.github.com/repos/{owner}/{repo}/git/refs/heads/{from_branch}"
        ref_response = self.session.get(ref_url, headers=headers)
        ref_response.raise_for_status()
        source_sha = ref_response.json()["object"]["sha"]

        # Create new branch
        create_ref_url = f"https://api.github.com/repos/{owner}/{repo}/git/refs"
        create_response = self.session.post(create_ref_url, headers=headers, json={
            "ref": f"refs/heads/{new_branch}",
            "sha": source_sha
        })
        create_response.raise_for_status()

        return {
            "success": True,
            "data": {
                "branch": new_branch,
                "sha": source_sha,
                "created_from": from_branch
            }
        }

    def _github_search_code(self, args: Dict, headers: Dict) -> Dict:
        """Search code on GitHub."""
        url = "https://api.github.com/search/code"
        params = {
            "q": args["query"],
            "per_page": args.get("per_page", 30)
        }

        response = self.session.get(url, headers=headers, params=params)
        response.raise_for_status()
        return {"success": True, "data": response.json()}

    def _github_search_issues(self, args: Dict, headers: Dict) -> Dict:
        """Search issues and PRs on GitHub."""
        url = "https://api.github.com/search/issues"
        params = {
            "q": args["query"],
            "per_page": args.get("per_page", 30)
        }

        response = self.session.get(url, headers=headers, params=params)
        response.raise_for_status()
        return {"success": True, "data": response.json()}

    def close(self):
        """Close the HTTP session."""
        if self._session:
            self._session.close()
            self._session = None
