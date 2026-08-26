"""GitHub API service for repository operations.

This service handles all GitHub API interactions for the code sessions feature.
It uses the GitHub REST API with OAuth tokens stored in GitHubConnection.
"""

import logging
from typing import Any, Optional, cast

import httpx
from django.conf import settings

logger = logging.getLogger(__name__)


class GitHubAPIError(Exception):
    """Exception raised for GitHub API errors."""

    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        response: Optional[dict] = None,
    ):
        self.message = message
        self.status_code = status_code
        self.response = response
        super().__init__(self.message)


class GitHubService:
    """Service for GitHub API operations.

    Handles repository listing, branch management, and authentication
    for the code sessions feature.
    """

    BASE_URL = "https://api.github.com"
    OAUTH_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
    OAUTH_TOKEN_URL = "https://github.com/login/oauth/access_token"

    # Default scopes for code operations
    DEFAULT_SCOPES = ["repo", "user:email"]

    def __init__(self, access_token: str):
        """Initialize with OAuth access token.

        Args:
            access_token: GitHub OAuth access token
        """
        self.access_token = access_token
        self._client: Optional[httpx.AsyncClient] = None

    @property
    def client(self) -> httpx.AsyncClient:
        """Get or create the HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                headers={
                    "Authorization": f"Bearer {self.access_token}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
                timeout=30.0,
            )
        return self._client

    async def close(self):
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()

    def _handle_response(self, response: httpx.Response) -> dict | list:
        """Handle API response, raising appropriate errors."""
        if response.status_code == 401:
            raise GitHubAPIError(
                "GitHub authentication failed. Please reconnect your account.",
                status_code=401,
            )
        elif response.status_code == 403:
            # Check for rate limiting
            if "rate limit" in response.text.lower():
                raise GitHubAPIError(
                    "GitHub API rate limit exceeded. Please try again later.",
                    status_code=403,
                )
            raise GitHubAPIError(
                "Access denied. You may not have permission for this repository.",
                status_code=403,
            )
        elif response.status_code == 404:
            raise GitHubAPIError(
                "Resource not found on GitHub.",
                status_code=404,
            )
        elif response.status_code >= 400:
            raise GitHubAPIError(
                f"GitHub API error: {response.text}",
                status_code=response.status_code,
                response=response.json() if response.text else None,
            )

        return response.json() if response.text else {}

    # ==================== User Operations ====================

    async def get_user(self) -> dict:
        """Get authenticated user info.

        Returns:
            dict: User information including login, id, name, email, avatar_url
        """
        response = await self.client.get(f"{self.BASE_URL}/user")
        return cast(dict, self._handle_response(response))

    async def get_user_emails(self) -> list[dict]:
        """Get authenticated user's email addresses.

        Returns:
            list: List of email objects with email, primary, verified fields
        """
        response = await self.client.get(f"{self.BASE_URL}/user/emails")
        return cast(list, self._handle_response(response))

    async def get_primary_email(self) -> str | None:
        """Get the user's primary verified email.

        Returns:
            str | None: Primary email address or None
        """
        emails = await self.get_user_emails()
        for email in emails:
            if email.get("primary") and email.get("verified"):
                return email.get("email")
        # Fallback to any verified email
        for email in emails:
            if email.get("verified"):
                return email.get("email")
        return None

    # ==================== Repository Operations ====================

    async def list_repos(
        self,
        page: int = 1,
        per_page: int = 30,
        sort: str = "pushed",
        direction: str = "desc",
        type: str = "all",
    ) -> list[dict]:
        """List user's repositories.

        Args:
            page: Page number for pagination
            per_page: Number of results per page (max 100)
            sort: Sort field (created, updated, pushed, full_name)
            direction: Sort direction (asc, desc)
            type: Repository type (all, owner, public, private, member)

        Returns:
            list: List of repository objects
        """
        response = await self.client.get(
            f"{self.BASE_URL}/user/repos",
            params={
                "sort": sort,
                "direction": direction,
                "page": page,
                "per_page": min(per_page, 100),
                "type": type,
            },
        )
        return cast(list, self._handle_response(response))

    async def get_repo(self, owner: str, repo: str) -> dict:
        """Get repository details.

        Args:
            owner: Repository owner (username or org)
            repo: Repository name

        Returns:
            dict: Repository details
        """
        response = await self.client.get(f"{self.BASE_URL}/repos/{owner}/{repo}")
        return cast(dict, self._handle_response(response))

    async def list_branches(
        self,
        owner: str,
        repo: str,
        page: int = 1,
        per_page: int = 100,
    ) -> list[dict]:
        """List repository branches.

        Args:
            owner: Repository owner
            repo: Repository name
            page: Page number
            per_page: Results per page

        Returns:
            list: List of branch objects with name and commit info
        """
        response = await self.client.get(
            f"{self.BASE_URL}/repos/{owner}/{repo}/branches",
            params={
                "page": page,
                "per_page": min(per_page, 100),
            },
        )
        return cast(list, self._handle_response(response))

    async def get_default_branch(self, owner: str, repo: str) -> str:
        """Get repository's default branch name.

        Args:
            owner: Repository owner
            repo: Repository name

        Returns:
            str: Default branch name (e.g., 'main', 'master')
        """
        repo_info = await self.get_repo(owner, repo)
        return repo_info.get("default_branch", "main")

    # ==================== Issue Operations ====================

    async def list_issues(
        self,
        owner: str,
        repo: str,
        state: str = "open",
        page: int = 1,
        per_page: int = 30,
    ) -> list[dict]:
        """List repository issues.

        Args:
            owner: Repository owner
            repo: Repository name
            state: Issue state (open, closed, all)
            page: Page number
            per_page: Results per page

        Returns:
            list: List of issue objects
        """
        response = await self.client.get(
            f"{self.BASE_URL}/repos/{owner}/{repo}/issues",
            params={
                "state": state,
                "page": page,
                "per_page": min(per_page, 100),
                "sort": "updated",
                "direction": "desc",
            },
        )
        # Filter out pull requests (GitHub API returns PRs as issues too)
        issues = self._handle_response(response)
        return [issue for issue in issues if "pull_request" not in issue]

    # ==================== Pull Request Operations ====================

    async def create_pull_request(
        self,
        owner: str,
        repo: str,
        title: str,
        body: str,
        head: str,
        base: Optional[str] = None,
        draft: bool = False,
    ) -> dict:
        """Create a pull request.

        Args:
            owner: Repository owner
            repo: Repository name
            title: PR title
            body: PR description (markdown)
            head: Branch containing changes
            base: Target branch (defaults to repo default)
            draft: Whether to create as draft

        Returns:
            dict: Created pull request object
        """
        if base is None:
            base = await self.get_default_branch(owner, repo)

        response = await self.client.post(
            f"{self.BASE_URL}/repos/{owner}/{repo}/pulls",
            json={
                "title": title,
                "body": body,
                "head": head,
                "base": base,
                "draft": draft,
            },
        )
        return cast(dict, self._handle_response(response))

    async def list_pull_requests(
        self,
        owner: str,
        repo: str,
        state: str = "open",
        page: int = 1,
        per_page: int = 30,
    ) -> list[dict]:
        """List pull requests for a repository.

        Args:
            owner: Repository owner
            repo: Repository name
            state: PR state (open, closed, all)
            page: Page number
            per_page: Results per page

        Returns:
            list: List of pull request objects
        """
        response = await self.client.get(
            f"{self.BASE_URL}/repos/{owner}/{repo}/pulls",
            params={
                "state": state,
                "page": page,
                "per_page": min(per_page, 100),
            },
        )
        return cast(list, self._handle_response(response))

    # ==================== Commit Operations ====================

    async def list_commits(
        self,
        owner: str,
        repo: str,
        branch: Optional[str] = None,
        limit: int = 20,
    ) -> list[dict]:
        """List commits for a repository branch.

        Args:
            owner: Repository owner
            repo: Repository name
            branch: Branch name (defaults to repo default)
            limit: Max number of commits to return

        Returns:
            list: List of commit objects
        """
        params: dict[str, Any] = {"per_page": min(limit, 100)}
        if branch:
            params["sha"] = branch

        response = await self.client.get(
            f"{self.BASE_URL}/repos/{owner}/{repo}/commits",
            params=params,
        )
        return cast(list, self._handle_response(response))

    async def compare_commits(
        self,
        owner: str,
        repo: str,
        base: str,
        head: str,
    ) -> dict:
        """Compare two commits/branches and get the diff.

        Args:
            owner: Repository owner
            repo: Repository name
            base: Base commit/branch
            head: Head commit/branch

        Returns:
            dict: Comparison result with files, commits, and diff info
        """
        response = await self.client.get(
            f"{self.BASE_URL}/repos/{owner}/{repo}/compare/{base}...{head}",
        )
        return cast(dict, self._handle_response(response))

    async def get_commit(
        self,
        owner: str,
        repo: str,
        sha: str,
    ) -> dict:
        """Get a specific commit with diff.

        Args:
            owner: Repository owner
            repo: Repository name
            sha: Commit SHA

        Returns:
            dict: Commit details with files and patches
        """
        response = await self.client.get(
            f"{self.BASE_URL}/repos/{owner}/{repo}/commits/{sha}",
        )
        return cast(dict, self._handle_response(response))

    # ==================== Git Operations Helpers ====================

    def get_clone_url_with_token(self, repo_url: str) -> str:
        """Get clone URL with embedded OAuth token for authenticated clone.

        Args:
            repo_url: GitHub repository URL (https://github.com/owner/repo or owner/repo)

        Returns:
            str: Clone URL with embedded token
        """
        # Handle full URL
        if repo_url.startswith("https://github.com/"):
            path = repo_url.replace("https://github.com/", "")
        elif repo_url.startswith("git@github.com:"):
            path = repo_url.replace("git@github.com:", "")
        else:
            path = repo_url

        # Remove .git suffix if present
        if path.endswith(".git"):
            path = path[:-4]

        return f"https://oauth2:{self.access_token}@github.com/{path}.git"

    def get_authenticated_remote_url(self, owner: str, repo: str) -> str:
        """Get authenticated remote URL for git operations.

        Args:
            owner: Repository owner
            repo: Repository name

        Returns:
            str: Authenticated git remote URL
        """
        return f"https://oauth2:{self.access_token}@github.com/{owner}/{repo}.git"

    # ==================== OAuth Helpers ====================

    @classmethod
    def get_authorization_url(cls, state: str, redirect_uri: Optional[str] = None) -> str:
        """Generate GitHub OAuth authorization URL.

        Args:
            state: CSRF state parameter
            redirect_uri: OAuth callback URL (optional)

        Returns:
            str: Authorization URL to redirect user to
        """
        params = {
            "client_id": settings.GITHUB_OAUTH_CLIENT_ID,
            "scope": " ".join(cls.DEFAULT_SCOPES),
            "state": state,
        }
        if redirect_uri:
            params["redirect_uri"] = redirect_uri

        query = "&".join(f"{k}={v}" for k, v in params.items())
        return f"{cls.OAUTH_AUTHORIZE_URL}?{query}"

    @classmethod
    async def exchange_code_for_token(cls, code: str) -> dict:
        """Exchange authorization code for access token.

        Args:
            code: Authorization code from OAuth callback

        Returns:
            dict: Token response with access_token, token_type, scope
        """
        async with httpx.AsyncClient() as client:
            response = await client.post(
                cls.OAUTH_TOKEN_URL,
                data={
                    "client_id": settings.GITHUB_OAUTH_CLIENT_ID,
                    "client_secret": settings.GITHUB_OAUTH_CLIENT_SECRET,
                    "code": code,
                },
                headers={
                    "Accept": "application/json",
                },
            )

            if response.status_code != 200:
                raise GitHubAPIError(
                    "Failed to exchange code for token",
                    status_code=response.status_code,
                    response=response.json() if response.text else None,
                )

            data = response.json()
            if "error" in data:
                raise GitHubAPIError(
                    data.get("error_description", data.get("error")),
                    response=data,
                )

            return data


def parse_repo_full_name(full_name: str) -> tuple[str, str]:
    """Parse owner and repo from full name.

    Args:
        full_name: Repository full name (owner/repo)

    Returns:
        tuple: (owner, repo)

    Raises:
        ValueError: If full_name is invalid
    """
    if "/" not in full_name:
        raise ValueError(f"Invalid repository name: {full_name}")

    parts = full_name.split("/")
    if len(parts) != 2:
        raise ValueError(f"Invalid repository name: {full_name}")

    return parts[0], parts[1]
