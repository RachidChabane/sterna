"""OAuth Protected Resource and Authorization Server metadata discovery.

Implements the discovery half of the MCP Authorization specification:

* OAuth 2.0 Protected Resource Metadata, RFC 9728 — locates the
  authorization server(s) that protect an MCP server, either from the
  `resource_metadata` parameter of a `WWW-Authenticate` challenge or
  from the RFC 9728 well-known URIs.
* Authorization Server Metadata discovery — given an authorization
  server's issuer URL, tries OAuth 2.0 Authorization Server Metadata
  (RFC 8414) and OpenID Connect Discovery 1.0 well-known endpoints in
  the priority order the MCP spec requires, and validates the returned
  `issuer` against the URL used to fetch it.

Kept separate from `oauth.py` so that module stays focused on the
PKCE/token-exchange flow that consumes this discovery output.
"""

import logging
import re
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import httpx

from .versioning import PREFERRED_PROTOCOL_VERSION

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 30.0

_PROBE_CLIENT_INFO: Dict[str, str] = {"name": "Sterna MCP Client", "version": "1.0.0"}

# Matches one `key="value"` (or unquoted `key=value`) pair inside a
# `WWW-Authenticate: Bearer ...` challenge.
_CHALLENGE_PARAM_RE = re.compile(r'(\w+)=(?:"([^"]*)"|([^\s,]+))')


def parse_www_authenticate(header_value: str) -> Dict[str, str]:
    """Extract the parameters of a `Bearer` `WWW-Authenticate` challenge.

    Returns an empty dict for a missing header or a non-Bearer scheme.
    """
    if not header_value or not header_value.strip().lower().startswith("bearer"):
        return {}
    params: Dict[str, str] = {}
    for key, quoted, unquoted in _CHALLENGE_PARAM_RE.findall(header_value):
        params[key] = quoted if quoted else unquoted
    return params


def canonical_resource_uri(url: str) -> str:
    """Canonical MCP server URI for RFC 8707 `resource` parameters.

    Lowercases scheme and host and drops a trailing slash, per the MCP
    Authorization spec's guidance; the caller is responsible for
    rejecting URLs with a fragment before this point.
    """
    parsed = urlparse(url)
    netloc = parsed.netloc.lower()
    path = parsed.path.rstrip("/")
    return f"{parsed.scheme.lower()}://{netloc}{path}"


def _protected_resource_well_known_urls(server_url: str) -> List[str]:
    """RFC 9728 well-known URIs for `server_url`, path-based then root."""
    parsed = urlparse(server_url)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    path = parsed.path.rstrip("/")
    urls = []
    if path:
        urls.append(f"{origin}/.well-known/oauth-protected-resource{path}")
    urls.append(f"{origin}/.well-known/oauth-protected-resource")
    return urls


async def _probe_unauthenticated(
    client: httpx.AsyncClient, server_url: str
) -> Optional[httpx.Response]:
    """Send an unauthenticated `initialize` request to observe a 401.

    Returns None on any transport failure — callers fall back to
    well-known URI probing rather than treating this as fatal.
    """
    probe_body = {
        "jsonrpc": "2.0",
        "id": "oauth-discovery-probe",
        "method": "initialize",
        "params": {
            "protocolVersion": PREFERRED_PROTOCOL_VERSION,
            "clientInfo": _PROBE_CLIENT_INFO,
            "capabilities": {},
        },
    }
    try:
        return await client.post(
            server_url,
            json=probe_body,
            headers={"Accept": "application/json, text/event-stream"},
        )
    except httpx.RequestError as e:
        logger.debug(f"Unauthenticated probe of {server_url} failed: {e}")
        return None


async def discover_protected_resource_metadata(
    server_url: str, timeout: float = DEFAULT_TIMEOUT
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Locate and fetch the MCP server's Protected Resource Metadata.

    Returns a `(metadata, challenge_scope)` pair. `metadata` is None if
    no PRM document could be found by any mechanism. `challenge_scope`
    is the `scope` parameter from a `WWW-Authenticate` challenge, when
    one was observed — the spec's first-priority scope source.
    """
    async with httpx.AsyncClient(timeout=timeout) as client:
        candidate_urls: List[str] = []
        challenge_scope: Optional[str] = None

        probe = await _probe_unauthenticated(client, server_url)
        if probe is not None and probe.status_code == 401:
            challenge = parse_www_authenticate(probe.headers.get("www-authenticate", ""))
            challenge_scope = challenge.get("scope")
            if challenge.get("resource_metadata"):
                candidate_urls.append(challenge["resource_metadata"])

        candidate_urls.extend(_protected_resource_well_known_urls(server_url))

        for url in candidate_urls:
            try:
                response = await client.get(url, headers={"Accept": "application/json"})
            except httpx.RequestError as e:
                logger.debug(f"Protected resource metadata fetch failed for {url}: {e}")
                continue
            if response.status_code == 200:
                try:
                    return response.json(), challenge_scope
                except ValueError:
                    logger.warning(f"Protected resource metadata at {url} was not valid JSON")
                    continue

        return None, challenge_scope


def _authorization_server_metadata_urls(issuer_url: str) -> List[str]:
    """Candidate metadata URLs for `issuer_url`, in the MCP spec's order."""
    parsed = urlparse(issuer_url)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    path = parsed.path.rstrip("/")

    if path:
        return [
            f"{origin}/.well-known/oauth-authorization-server{path}",
            f"{origin}/.well-known/openid-configuration{path}",
            f"{origin}{path}/.well-known/openid-configuration",
        ]
    return [
        f"{origin}/.well-known/oauth-authorization-server",
        f"{origin}/.well-known/openid-configuration",
    ]


async def discover_authorization_server_metadata(
    issuer_url: str, timeout: float = DEFAULT_TIMEOUT
) -> Optional[Dict[str, Any]]:
    """Discover OAuth/OIDC metadata for the authorization server at `issuer_url`.

    Tries RFC 8414 and OpenID Connect Discovery well-known endpoints in
    priority order, and rejects any document whose declared `issuer`
    does not exactly match `issuer_url` (RFC 8414 Section 3.3 /
    OpenID Connect Discovery Section 4.3) to prevent a metadata
    document from one origin being trusted for another.
    """
    async with httpx.AsyncClient(timeout=timeout) as client:
        for url in _authorization_server_metadata_urls(issuer_url):
            try:
                response = await client.get(url, headers={"Accept": "application/json"})
            except httpx.RequestError as e:
                logger.debug(f"Authorization server metadata fetch failed for {url}: {e}")
                continue
            if response.status_code != 200:
                continue
            try:
                data = response.json()
            except ValueError:
                logger.warning(f"Authorization server metadata at {url} was not valid JSON")
                continue
            if data.get("issuer") != issuer_url:
                logger.warning(
                    f"Rejecting authorization server metadata at {url}: "
                    f"issuer {data.get('issuer')!r} does not match {issuer_url!r}"
                )
                continue
            return data

    return None
