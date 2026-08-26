"""MCP Server Configuration Helper.

Uses LLM to extract configuration requirements from MCP server documentation.
Fetches README from npm registry or GitHub and extracts env vars, auth setup, etc.
"""

import logging
import re
from dataclasses import dataclass
from typing import Optional

import httpx

from llm.generation_models import get_generation_assistant_model, log_generation_usage

logger = logging.getLogger(__name__)


@dataclass
class ConfigRequirement:
    """A single configuration requirement (env var, auth field, etc.)."""
    name: str
    label: str
    description: str
    required: bool = True
    secret: bool = False
    example: Optional[str] = None
    docs_url: Optional[str] = None


@dataclass
class ConfigHelp:
    """Configuration help for an MCP server."""
    server_name: str
    env_vars: list[ConfigRequirement]
    auth_info: Optional[str] = None
    setup_steps: Optional[list[str]] = None
    docs_url: Optional[str] = None
    allowed_domains: Optional[list[str]] = None  # Domains the server needs to access
    auth_type: Optional[str] = None  # none, api_key, bearer, oauth
    compatibility_warning: Optional[str] = None  # Warning if server may not work in cloud
    raw_readme: Optional[str] = None  # For debugging


async def fetch_npm_readme(package_name: str) -> Optional[str]:
    """Fetch README from npm registry.

    Args:
        package_name: NPM package name (e.g., '@modelcontextprotocol/server-github')

    Returns:
        README content if found, None otherwise
    """
    try:
        # npm registry API
        # For scoped packages like @org/pkg, the URL is /@org%2Fpkg
        encoded_name = package_name.replace("/", "%2F")
        url = f"https://registry.npmjs.org/{encoded_name}"

        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(url)

            if response.status_code != 200:
                logger.warning(f"npm registry returned {response.status_code} for {package_name}")
                return None

            data = response.json()
            readme = data.get("readme", "")

            if readme:
                logger.info(f"Fetched README from npm for {package_name} ({len(readme)} chars)")
                return readme

            # Try to get from latest version
            latest_version = data.get("dist-tags", {}).get("latest")
            if latest_version and latest_version in data.get("versions", {}):
                version_data = data["versions"][latest_version]
                readme = version_data.get("readme", "")
                if readme:
                    return readme

            return None

    except Exception as e:
        logger.warning(f"Failed to fetch npm README for {package_name}: {e}")
        return None


async def fetch_github_readme(repo_url: str) -> Optional[str]:
    """Fetch README from GitHub repository.

    Args:
        repo_url: GitHub repository URL (e.g., 'https://github.com/org/repo')

    Returns:
        README content if found, None otherwise
    """
    try:
        # Extract owner/repo from URL
        match = re.search(r"github\.com[/:]([^/]+)/([^/]+?)(?:\.git)?$", repo_url)
        if not match:
            return None

        owner, repo = match.groups()

        # Try common README filenames
        readme_files = ["README.md", "readme.md", "README", "readme.markdown"]

        async with httpx.AsyncClient(timeout=15.0) as client:
            for readme_file in readme_files:
                url = f"https://raw.githubusercontent.com/{owner}/{repo}/main/{readme_file}"
                response = await client.get(url)

                if response.status_code == 200:
                    logger.info(f"Fetched README from GitHub for {owner}/{repo}")
                    return response.text

                # Try master branch
                url = f"https://raw.githubusercontent.com/{owner}/{repo}/master/{readme_file}"
                response = await client.get(url)

                if response.status_code == 200:
                    logger.info(f"Fetched README from GitHub for {owner}/{repo}")
                    return response.text

        return None

    except Exception as e:
        logger.warning(f"Failed to fetch GitHub README for {repo_url}: {e}")
        return None


async def extract_config_with_llm(
    readme: str,
    server_name: str,
    npm_package: Optional[str] = None,
    user=None,
) -> ConfigHelp:
    """Use LLM to extract configuration requirements from README.

    Args:
        readme: README content
        server_name: Name of the MCP server
        npm_package: NPM package name (optional, for context)
        user: User object for API key resolution

    Returns:
        ConfigHelp with extracted configuration requirements
    """
    import json
    from llm.services.api_key_resolver import get_api_key_with_fallback

    # Truncate README if too long (save tokens)
    max_readme_len = 8000
    if len(readme) > max_readme_len:
        readme = readme[:max_readme_len] + "\n\n[README truncated...]"

    prompt = f"""You are helping users configure an MCP server in our platform.

IMPORTANT CONTEXT ABOUT OUR PLATFORM:
- Our platform runs MCP servers automatically in sandboxed Docker containers
- Users do NOT need to install anything (no npm, no UV, no Go, no Python, etc.)
- Users do NOT need to run any commands (no npx, no uvx, no terminal commands)
- Users do NOT need to restart any applications
- Users do NOT need to configure Claude Desktop, Cursor, or any other app
- The ONLY thing users need to provide is:
  1. Environment variables (API keys, tokens, credentials)
  2. Any required authentication credentials
- Our platform handles ALL installation, execution, and lifecycle management

Server name: {server_name}
NPM package: {npm_package or 'N/A'}

README:
```
{readme}
```

Extract and return a JSON object with:
1. "env_vars": Array of environment variables needed. For each:
   - "name": The exact env var name (e.g., "GITHUB_PERSONAL_ACCESS_TOKEN")
   - "label": Human-friendly label (e.g., "GitHub Personal Access Token")
   - "description": Brief description of what it's for and how to get it
   - "required": true/false
   - "secret": true if it's a sensitive value like API key/token
   - "example": Example value format (optional, mask sensitive parts)
   - "docs_url": URL where user can create/get the token/key (optional)

2. "auth_info": Brief description of authentication method. Focus ONLY on what credentials the user needs to obtain (e.g., "Requires a GitHub Personal Access Token with repo scope"). Do NOT mention installation steps, QR codes for local apps, or any local setup procedures.

3. "setup_steps": Array of steps the user needs to take BEFORE connecting. ONLY include:
   - How to create/obtain API keys or tokens (e.g., "Go to github.com/settings/tokens")
   - What permissions/scopes to grant (e.g., "Enable 'repo' and 'read:user' scopes")
   - Account setup if required (e.g., "Create a Notion integration at notion.so/my-integrations")
   DO NOT include any of these (our platform handles them automatically):
   - Installing software (npm, Go, Python, UV, etc.)
   - Running commands (npx, uvx, npm install, etc.)
   - Configuration file editing
   - Starting servers or bridges
   - Restarting applications
   - QR code scanning for local authentication

4. "docs_url": Main documentation URL where user can learn more

5. "allowed_domains": Array of API domains the server needs to access (e.g., ["api.github.com"]). Infer from the service being connected to.

6. "compatibility_warning": (optional) If the server requires authentication methods we can't support (e.g., QR code scanning, local file access, desktop app integration), set this to a SHORT, simple warning. Keep it non-technical, under 15 words, and include "for now" to hint at future support. Examples:
   - "Not available for now — requires QR code scanning."
   - "Not available yet — requires local file access."
   - "Coming soon — currently requires a desktop app."
   Do NOT mention cloud, sandbox, containers, infrastructure, or any technical details.

Return ONLY valid JSON, no markdown or explanation. If no env vars are needed, return empty array.
Example format:
{{
  "env_vars": [
    {{
      "name": "GITHUB_PERSONAL_ACCESS_TOKEN",
      "label": "Personal Access Token",
      "description": "GitHub PAT with repo and read:user access",
      "required": true,
      "secret": true,
      "docs_url": "https://github.com/settings/tokens"
    }}
  ],
  "auth_info": "Requires a GitHub Personal Access Token for API access",
  "setup_steps": [
    "Go to github.com/settings/tokens and click 'Generate new token'",
    "Select scopes: 'repo' (full access) and 'read:user'",
    "Copy the generated token and paste it in the configuration form"
  ],
  "docs_url": "https://github.com/modelcontextprotocol/servers",
  "allowed_domains": ["api.github.com", "raw.githubusercontent.com"]
}}"""

    try:
        # Use centralized API key resolver
        api_key = get_api_key_with_fallback(user=user)

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": get_generation_assistant_model(),
                    "messages": [
                        {"role": "user", "content": prompt}
                    ],
                    "max_tokens": 1500,
                    "temperature": 0.1,  # Low temperature for structured extraction
                },
            )

            if response.status_code != 200:
                logger.error(f"OpenRouter API error: {response.status_code} - {response.text}")
                raise Exception(f"OpenRouter API error: {response.status_code}")

            data = response.json()
            log_generation_usage(data, get_generation_assistant_model(), user=user, request_source="mcp_config_help")
            content = data["choices"][0]["message"]["content"].strip()

        # Try to parse JSON (handle markdown code blocks)
        if content.startswith("```"):
            # Extract JSON from code block
            content = re.sub(r"^```(?:json)?\n?", "", content)
            content = re.sub(r"\n?```$", "", content)

        parsed = json.loads(content)

        env_vars = []
        for ev in parsed.get("env_vars", []):
            env_vars.append(ConfigRequirement(
                name=ev.get("name", ""),
                label=ev.get("label", ev.get("name", "")),
                description=ev.get("description", ""),
                required=ev.get("required", True),
                secret=ev.get("secret", False),
                example=ev.get("example"),
                docs_url=ev.get("docs_url"),
            ))

        return ConfigHelp(
            server_name=server_name,
            env_vars=env_vars,
            auth_info=parsed.get("auth_info"),
            setup_steps=parsed.get("setup_steps", []),
            docs_url=parsed.get("docs_url"),
            allowed_domains=parsed.get("allowed_domains", []),
            compatibility_warning=parsed.get("compatibility_warning"),
        )

    except json.JSONDecodeError as e:
        logger.warning(f"Failed to parse LLM response as JSON: {e}")
        # Return empty config help
        return ConfigHelp(
            server_name=server_name,
            env_vars=[],
            auth_info="Could not extract configuration from README",
            setup_steps=["Please refer to the server documentation"],
            allowed_domains=[],
        )
    except Exception as e:
        logger.error(f"LLM config extraction failed: {e}")
        raise


async def search_web_for_server_info(query: str) -> list[dict]:
    """Search the web for information about an MCP server.

    Args:
        query: Search query (e.g., server URL or name)

    Returns:
        List of search results with titles and descriptions
    """
    import os

    brave_api_key = os.getenv("BRAVE_API_KEY")
    if not brave_api_key:
        logger.warning("BRAVE_API_KEY not set, cannot search web")
        return []

    # Construct search query focused on MCP server configuration
    search_query = f"MCP server {query} configuration authentication API"

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                "https://api.search.brave.com/res/v1/web/search",
                headers={
                    "X-Subscription-Token": brave_api_key,
                    "Accept": "application/json",
                },
                params={
                    "q": search_query,
                    "count": 5,
                    "safesearch": "moderate",
                },
            )

            if response.status_code != 200:
                logger.warning(f"Brave Search returned {response.status_code}")
                return []

            data = response.json()
            results = []

            for result in data.get("web", {}).get("results", []):
                results.append({
                    "title": result.get("title", ""),
                    "description": result.get("description", ""),
                    "url": result.get("url", ""),
                })

            logger.info(f"Found {len(results)} search results for: {query}")
            return results

    except Exception as e:
        logger.warning(f"Web search failed: {e}")
        return []


async def extract_config_from_search_results(
    search_results: list[dict],
    server_name: str,
    remote_url: str,
    user=None,
) -> ConfigHelp:
    """Use LLM to extract config requirements from web search results.

    Args:
        search_results: Web search results
        server_name: Name of the MCP server
        remote_url: The remote server URL
        user: User object for API key resolution

    Returns:
        ConfigHelp with extracted requirements
    """
    import json
    from llm.services.api_key_resolver import get_api_key_with_fallback

    # Format search results
    results_text = ""
    for i, result in enumerate(search_results[:5], 1):
        results_text += f"""
Result {i}:
- Title: {result.get('title', 'N/A')}
- URL: {result.get('url', 'N/A')}
- Description: {result.get('description', 'N/A')}
"""

    # Extract domain from URL for context
    from urllib.parse import urlparse
    parsed = urlparse(remote_url)
    domain = parsed.netloc

    prompt = f"""You are helping users configure a remote MCP server in our platform.

IMPORTANT CONTEXT ABOUT OUR PLATFORM:
- Our platform connects to remote MCP servers via HTTP
- Users need to provide authentication credentials (API keys, OAuth tokens, etc.)
- We handle the connection automatically

Server URL: {remote_url}
Domain: {domain}
Server name: {server_name}

Here is information found about this MCP server:
{results_text if results_text.strip() else "No search results found. Use your knowledge about the domain/service."}

Based on this information (and your knowledge about {domain}), extract:

1. "env_vars": Array of credentials/tokens needed. For each:
   - "name": The variable name (e.g., "ZAPIER_API_KEY")
   - "label": Human-friendly label
   - "description": Brief description and how to get it
   - "required": true/false
   - "secret": true if sensitive
   - "docs_url": URL to get the credential (optional)

2. "auth_info": Brief description of authentication method

3. "setup_steps": Steps to get the required credentials. ONLY include:
   - How to create/obtain API keys or tokens
   - What permissions/scopes to grant
   DO NOT include installation or command-line steps.

4. "docs_url": Documentation URL if found

5. "auth_type": The authentication method. One of: "none", "api_key", "bearer", "oauth". Use "oauth" if the server uses OAuth 2.0.

6. "compatibility_warning": (optional) If authentication isn't possible (e.g., requires desktop app), set a SHORT warning under 15 words with "for now" to hint at future support. Examples:
   - "Not available for now — requires QR code scanning."
   Do NOT mention cloud, sandbox, or technical details.

IMPORTANT: If the server uses OAuth:
- Set "auth_type" to "oauth"
- Set "auth_info" to exactly: "Make sure \"OAuth 2.0\" is selected below and click Connect Server — that's it!"
- Set "setup_steps" to an empty array []
- Do NOT explain what OAuth is or how it works - just tell the user to proceed

Return ONLY valid JSON.
{{
  "env_vars": [...],
  "auth_info": "...",
  "setup_steps": [...],
  "docs_url": "...",
  "auth_type": "oauth",
  "compatibility_warning": null
}}"""

    try:
        api_key = get_api_key_with_fallback(user=user)

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": get_generation_assistant_model(),
                    "messages": [
                        {"role": "user", "content": prompt}
                    ],
                    "max_tokens": 1500,
                    "temperature": 0.1,
                },
            )

            if response.status_code != 200:
                logger.error(f"OpenRouter API error: {response.status_code}")
                raise Exception(f"OpenRouter API error: {response.status_code}")

            data = response.json()
            log_generation_usage(data, get_generation_assistant_model(), user=user, request_source="mcp_config_help")
            content = data["choices"][0]["message"]["content"].strip()

        # Parse JSON
        if content.startswith("```"):
            content = re.sub(r"^```(?:json)?\n?", "", content)
            content = re.sub(r"\n?```$", "", content)

        parsed_data = json.loads(content)

        env_vars = []
        for ev in parsed_data.get("env_vars", []):
            env_vars.append(ConfigRequirement(
                name=ev.get("name", ""),
                label=ev.get("label", ev.get("name", "")),
                description=ev.get("description", ""),
                required=ev.get("required", True),
                secret=ev.get("secret", False),
                example=ev.get("example"),
                docs_url=ev.get("docs_url"),
            ))

        return ConfigHelp(
            server_name=server_name,
            env_vars=env_vars,
            auth_info=parsed_data.get("auth_info"),
            setup_steps=parsed_data.get("setup_steps", []),
            docs_url=parsed_data.get("docs_url"),
            allowed_domains=[domain] if domain else [],
            auth_type=parsed_data.get("auth_type"),
            compatibility_warning=parsed_data.get("compatibility_warning"),
        )

    except json.JSONDecodeError as e:
        logger.warning(f"Failed to parse LLM response for remote server: {e}")
        return ConfigHelp(
            server_name=server_name,
            env_vars=[],
            auth_info="Could not determine configuration requirements",
            setup_steps=["Check the server's documentation for authentication details"],
            allowed_domains=[domain] if domain else [],
        )
    except Exception as e:
        logger.error(f"Remote server config extraction failed: {e}")
        raise


async def get_config_help(
    server_name: str,
    npm_package: Optional[str] = None,
    remote_url: Optional[str] = None,
    github_url: Optional[str] = None,
    user=None,
) -> ConfigHelp:
    """Get configuration help for an MCP server.

    Fetches README from npm/GitHub or uses web search for remote servers.

    Args:
        server_name: Name of the MCP server
        npm_package: NPM package name (optional, for local servers)
        remote_url: Remote server URL (optional, for remote servers)
        github_url: GitHub repository URL (optional)
        user: User object for API key resolution

    Returns:
        ConfigHelp with configuration requirements
    """
    readme = None

    # For remote servers without npm package, use web search
    if remote_url and not npm_package:
        logger.info(f"Searching web for remote server info: {remote_url}")
        search_results = await search_web_for_server_info(remote_url)
        return await extract_config_from_search_results(
            search_results=search_results,
            server_name=server_name,
            remote_url=remote_url,
            user=user,
        )

    # Try npm first (most MCP servers are npm packages)
    if npm_package:
        readme = await fetch_npm_readme(npm_package)

    # Fall back to GitHub
    if not readme and github_url:
        readme = await fetch_github_readme(github_url)

    # If we still don't have a README, try to infer GitHub URL from npm package
    if not readme and npm_package:
        # Common pattern: @modelcontextprotocol/server-x -> github.com/modelcontextprotocol/servers
        if npm_package.startswith("@modelcontextprotocol/"):
            readme = await fetch_github_readme("https://github.com/modelcontextprotocol/servers")

    if not readme:
        logger.info(f"No README found for {server_name}, returning basic help")
        return ConfigHelp(
            server_name=server_name,
            env_vars=[],
            auth_info="No documentation found. Please check the server's documentation for configuration requirements.",
            setup_steps=[
                "Check the package documentation for required credentials",
            ],
        )

    # Extract config with LLM
    config_help = await extract_config_with_llm(
        readme=readme,
        server_name=server_name,
        npm_package=npm_package,
        user=user,
    )

    return config_help
