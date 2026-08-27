"""AI-powered MCP Server Discovery.

Uses web search and LLM to find and recommend MCP servers based on user's description.
"""

import logging
import os
import re
from dataclasses import dataclass, field
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# Model for AI discovery - easily changeable
AI_DISCOVERY_MODEL = "anthropic/claude-haiku-4.5"


@dataclass
class DiscoveredServer:
    """A discovered MCP server from AI search."""
    name: str
    description: str
    npm_package: Optional[str] = None
    remote_url: Optional[str] = None
    github_url: Optional[str] = None
    server_type: str = "local"  # "local" or "remote"
    auth_type: str = "none"  # "none", "api_key", "bearer", "oauth"
    confidence: float = 0.0  # 0-1 confidence score
    source_url: Optional[str] = None  # Where we found this info
    # For preconfigured servers
    preconfigured_id: Optional[str] = None
    icon_url: Optional[str] = None
    icon_invert_in_dark_mode: bool = False


@dataclass
class DiscoveryResult:
    """Result of AI-powered MCP server discovery."""
    preconfigured: list[DiscoveredServer] = field(default_factory=list)
    external: list[DiscoveredServer] = field(default_factory=list)


async def search_web_for_mcp_servers(query: str) -> list[dict]:
    """Search the web for MCP servers matching the query.

    Uses Brave Search API to find relevant MCP servers.

    Args:
        query: User's description of what they want to do

    Returns:
        List of search results with titles, descriptions, and URLs
    """
    brave_api_key = os.getenv("BRAVE_API_KEY")
    if not brave_api_key:
        logger.warning("BRAVE_API_KEY not set, using fallback search")
        return []

    # Construct search query focused on MCP servers
    search_query = f"MCP server {query} npm OR github modelcontextprotocol"

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
                    "count": 10,
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


async def analyze_with_llm(
    user_query: str,
    search_results: list[dict],
    user=None,
) -> list[DiscoveredServer]:
    """Use LLM to analyze search results and extract MCP server recommendations.

    Args:
        user_query: What the user wants to do
        search_results: Web search results to analyze
        user: User object for API key resolution

    Returns:
        List of discovered MCP servers with structured info
    """
    import json
    from llm.services.api_key_resolver import get_api_key_with_fallback

    api_key = get_api_key_with_fallback(user=user)

    # Format search results for the prompt
    results_text = ""
    for i, result in enumerate(search_results[:10], 1):
        results_text += f"""
Result {i}:
- Title: {result.get('title', 'N/A')}
- URL: {result.get('url', 'N/A')}
- Description: {result.get('description', 'N/A')}
"""

    prompt = f"""You are an expert at finding MCP (Model Context Protocol) servers.
A user wants to connect to external services and is looking for the right MCP server.

User's request: "{user_query}"

Here are web search results that might contain relevant MCP servers:
{results_text}

Based on these results, identify MCP servers that match the user's needs.
For each server found, extract:

1. "name": A friendly name for the server
2. "description": Brief description of what it does
3. "npm_package": NPM package name - REQUIRED for local servers. Common patterns:
   - @modelcontextprotocol/server-xxx (official servers)
   - @anthropic/mcp-server-xxx
   - mcp-server-xxx
   - For GitHub repos like "github.com/user/mcp-server-foo", the npm package is usually "mcp-server-foo" or "@user/mcp-server-foo"
4. "remote_url": HTTP/SSE endpoint URL for remote servers (e.g., "https://mcp.example.com/sse")
5. "github_url": GitHub repository URL if available
6. "server_type": "local" if npm_package is provided, "remote" if remote_url is provided
7. "auth_type": "none", "api_key", "bearer", or "oauth" - infer from the description
8. "confidence": 0.0-1.0 how confident you are this matches the user's needs
9. "source_url": The URL where you found this information

CRITICAL RULES:
- Every server MUST have either npm_package OR remote_url - never leave both empty
- For GitHub-based MCP servers, derive the npm_package from the repo name
- Most MCP servers are npm packages (local), only use remote_url for hosted HTTP endpoints
- If unsure about exact npm_package name, use the GitHub repo name as the package name

Return a JSON array of servers. If no relevant MCP servers are found, return an empty array [].
Return ONLY valid JSON, no markdown or explanation.

Example format:
[
  {{
    "name": "GitHub MCP Server",
    "description": "Interact with GitHub repositories, issues, pull requests",
    "npm_package": "@modelcontextprotocol/server-github",
    "github_url": "https://github.com/modelcontextprotocol/servers",
    "server_type": "local",
    "auth_type": "api_key",
    "confidence": 0.95,
    "source_url": "https://npmjs.com/package/@modelcontextprotocol/server-github"
  }},
  {{
    "name": "Zapier MCP",
    "description": "Connect to Zapier automations",
    "remote_url": "https://mcp.zapier.com/api/mcp/sse",
    "server_type": "remote",
    "auth_type": "oauth",
    "confidence": 0.9,
    "source_url": "https://zapier.com/mcp"
  }}
]"""

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": AI_DISCOVERY_MODEL,
                    "messages": [
                        {"role": "user", "content": prompt}
                    ],
                    "max_tokens": 2000,
                    "temperature": 0.2,
                },
            )

            if response.status_code != 200:
                logger.error(f"OpenRouter API error: {response.status_code} - {response.text}")
                raise Exception(f"OpenRouter API error: {response.status_code}")

            data = response.json()
            content = data["choices"][0]["message"]["content"].strip()

        # Parse JSON (handle markdown code blocks)
        if content.startswith("```"):
            content = re.sub(r"^```(?:json)?\n?", "", content)
            content = re.sub(r"\n?```$", "", content)

        parsed = json.loads(content)

        servers = []
        for item in parsed:
            server = DiscoveredServer(
                name=item.get("name", "Unknown"),
                description=item.get("description", ""),
                npm_package=item.get("npm_package"),
                remote_url=item.get("remote_url"),
                github_url=item.get("github_url"),
                server_type=item.get("server_type", "local"),
                auth_type=item.get("auth_type", "none"),
                confidence=float(item.get("confidence", 0.5)),
                source_url=item.get("source_url"),
            )
            servers.append(server)

        # Sort by confidence
        servers.sort(key=lambda s: s.confidence, reverse=True)

        logger.info(f"LLM found {len(servers)} MCP servers for: {user_query}")
        return servers

    except json.JSONDecodeError as e:
        logger.warning(f"Failed to parse LLM response as JSON: {e}")
        return []
    except Exception as e:
        logger.error(f"LLM analysis failed: {e}")
        raise


async def match_preconfigured_servers(
    user_query: str,
    preconfigured_servers: list[dict],
    user=None,
) -> list[DiscoveredServer]:
    """Use LLM to match user query against preconfigured servers.

    Args:
        user_query: What the user wants to do
        preconfigured_servers: List of preconfigured server dicts from database
        user: User object for API key resolution

    Returns:
        List of matching preconfigured servers with confidence scores
    """
    import json
    from llm.services.api_key_resolver import get_api_key_with_fallback

    if not preconfigured_servers:
        return []

    api_key = get_api_key_with_fallback(user=user)

    # Format preconfigured servers for the prompt
    servers_text = ""
    for i, server in enumerate(preconfigured_servers, 1):
        servers_text += f"""
Server {i}:
- ID: {server.get('id')}
- Name: {server.get('name')}
- Description: {server.get('description', 'N/A')}
- Category: {server.get('category', 'N/A')}
"""

    prompt = f"""You are matching a user's request to available MCP servers.

User's request: "{user_query}"

Available preconfigured MCP servers:
{servers_text}

For each server that matches the user's needs, return its ID and a confidence score (0.0-1.0).
Only include servers that are relevant to what the user wants to do.

Return a JSON array. If no servers match, return an empty array [].
Return ONLY valid JSON, no markdown or explanation.

Example format:
[
  {{"id": "abc123", "confidence": 0.95}},
  {{"id": "def456", "confidence": 0.7}}
]"""

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": AI_DISCOVERY_MODEL,
                    "messages": [
                        {"role": "user", "content": prompt}
                    ],
                    "max_tokens": 500,
                    "temperature": 0.1,
                },
            )

            if response.status_code != 200:
                logger.error(f"OpenRouter API error: {response.status_code}")
                return []

            data = response.json()
            content = data["choices"][0]["message"]["content"].strip()

        # Parse JSON
        if content.startswith("```"):
            content = re.sub(r"^```(?:json)?\n?", "", content)
            content = re.sub(r"\n?```$", "", content)

        parsed = json.loads(content)

        # Map back to server objects
        server_map = {str(s['id']): s for s in preconfigured_servers}
        results = []

        for match in parsed:
            server_id = str(match.get('id'))
            if server_id in server_map:
                server = server_map[server_id]
                results.append(DiscoveredServer(
                    name=server.get('name', 'Unknown'),
                    description=server.get('description', ''),
                    npm_package=server.get('npm_package'),
                    remote_url=server.get('remote_url'),
                    server_type='remote' if server.get('remote_url') else 'local',
                    auth_type=server.get('auth_type', 'none'),
                    confidence=float(match.get('confidence', 0.5)),
                    preconfigured_id=server_id,
                    icon_url=server.get('icon_url'),
                    icon_invert_in_dark_mode=server.get('icon_invert_in_dark_mode', False),
                ))

        # Sort by confidence
        results.sort(key=lambda s: s.confidence, reverse=True)
        return results

    except json.JSONDecodeError as e:
        logger.warning(f"Failed to parse LLM response for preconfigured matching: {e}")
        return []
    except Exception as e:
        logger.error(f"Preconfigured server matching failed: {e}")
        return []


async def discover_mcp_servers(
    user_query: str,
    preconfigured_servers: Optional[list[dict]] = None,
    user=None,
) -> DiscoveryResult:
    """Main entry point for AI-powered MCP server discovery.

    Args:
        user_query: Description of what the user wants to do
        preconfigured_servers: Optional list of preconfigured servers to search first
        user: User object for API key resolution

    Returns:
        DiscoveryResult with preconfigured and external server matches
    """
    result = DiscoveryResult()
    preconfigured_servers = preconfigured_servers or []

    # First, match against preconfigured servers
    if preconfigured_servers:
        result.preconfigured = await match_preconfigured_servers(
            user_query, preconfigured_servers, user=user
        )
        logger.info(f"Found {len(result.preconfigured)} matching preconfigured servers")

    # Then search the web for external servers
    search_results = await search_web_for_mcp_servers(user_query)

    # If no search results, still try LLM with built-in knowledge
    if not search_results:
        logger.info("No search results, using LLM's built-in knowledge")
        search_results = [
            {
                "title": "Model Context Protocol Servers",
                "url": "https://github.com/modelcontextprotocol/servers",
                "description": "Official MCP servers: GitHub, Slack, Google Drive, Filesystem, PostgreSQL, Brave Search, and more",
            },
            {
                "title": "MCP Server List - NPM",
                "url": "https://www.npmjs.com/search?q=%40modelcontextprotocol",
                "description": "NPM packages for MCP servers including @modelcontextprotocol/server-github, server-slack, server-filesystem",
            },
        ]

    # Analyze with LLM
    result.external = await analyze_with_llm(user_query, search_results, user=user)

    # Filter out external servers that exist in our catalog (check ALL preconfigured, not just matched)
    # This prevents duplicates where web search finds a server we already have
    catalog_packages = {s.get('npm_package') for s in preconfigured_servers if s.get('npm_package')}
    catalog_urls = {s.get('remote_url') for s in preconfigured_servers if s.get('remote_url')}
    catalog_names = {s.get('name', '').lower() for s in preconfigured_servers}

    def is_duplicate(server: DiscoveredServer) -> bool:
        # Check npm package match
        if server.npm_package and server.npm_package in catalog_packages:
            return True
        # Check remote URL match
        if server.remote_url and server.remote_url in catalog_urls:
            return True
        # Check name match (fuzzy - if name is very similar)
        if server.name.lower() in catalog_names:
            return True
        return False

    original_count = len(result.external)
    result.external = [s for s in result.external if not is_duplicate(s)]

    if original_count != len(result.external):
        logger.info(f"Filtered {original_count - len(result.external)} duplicate servers from external results")

    logger.info(f"Found {len(result.external)} external servers")
    return result
