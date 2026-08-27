"""OAuth for MCP servers.

Implements the MCP Authorization specification's dynamic OAuth flow:
per-server metadata discovery (RFC 9728 + RFC 8414), optional dynamic
client registration (RFC 7591), PKCE (RFC 7636), resource-scoped tokens
(RFC 8707), and token exchange/refresh. No provider-specific handler
layer — every remote MCP server authenticates through the same flow.
"""

import base64
import hashlib
import logging
import secrets
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional
from urllib.parse import urlencode, urlparse

import httpx
from asgiref.sync import sync_to_async
from django.conf import settings

from .oauth_metadata import (
    canonical_resource_uri,
    discover_authorization_server_metadata,
    discover_protected_resource_metadata,
)

logger = logging.getLogger(__name__)


# =============================================================================
# MCP Dynamic OAuth Discovery (MCP Authorization Spec)
# =============================================================================
#
# The following classes implement dynamic OAuth discovery for arbitrary MCP
# servers, following the MCP Authorization specification. This allows users
# to connect to ANY MCP server that supports OAuth without provider-specific
# configuration on our end.
#
# References:
# - MCP Authorization Spec: https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization
# - RFC 9728 (Protected Resource Metadata), RFC 8414 (AS Metadata),
#   RFC 8707 (Resource Indicators), RFC 7591 (Dynamic Client Registration),
#   RFC 7636 (PKCE)
# =============================================================================

if TYPE_CHECKING:
    from .models import MCPServer


@dataclass
class DynamicOAuthMetadata:
    """OAuth 2.0 Authorization Server Metadata (RFC 8414) for dynamic discovery."""

    issuer: str = ''
    authorization_endpoint: str = ''
    token_endpoint: str = ''
    registration_endpoint: str = ''  # For dynamic client registration
    revocation_endpoint: str = ''
    scopes_supported: list = field(default_factory=list)
    response_types_supported: list = field(default_factory=list)
    code_challenge_methods_supported: list = field(default_factory=list)
    token_endpoint_auth_methods_supported: list = field(default_factory=list)

    @classmethod
    def from_response(cls, data: dict) -> 'DynamicOAuthMetadata':
        """Create from OAuth server metadata response."""
        return cls(
            issuer=data.get('issuer', ''),
            authorization_endpoint=data.get('authorization_endpoint', ''),
            token_endpoint=data.get('token_endpoint', ''),
            registration_endpoint=data.get('registration_endpoint', ''),
            revocation_endpoint=data.get('revocation_endpoint', ''),
            scopes_supported=data.get('scopes_supported', []),
            response_types_supported=data.get('response_types_supported', ['code']),
            code_challenge_methods_supported=data.get('code_challenge_methods_supported', ['S256']),
            token_endpoint_auth_methods_supported=data.get('token_endpoint_auth_methods_supported', []),
        )

    @classmethod
    def with_defaults(cls, base_url: str) -> 'DynamicOAuthMetadata':
        """Create with fallback default endpoints."""
        return cls(
            issuer=base_url,
            authorization_endpoint=f"{base_url}/authorize",
            token_endpoint=f"{base_url}/token",
            registration_endpoint=f"{base_url}/register",
            scopes_supported=[],
            response_types_supported=['code'],
            code_challenge_methods_supported=['S256'],
        )

    def to_dict(self) -> dict:
        """Convert to dictionary for storage."""
        return {
            'issuer': self.issuer,
            'authorization_endpoint': self.authorization_endpoint,
            'token_endpoint': self.token_endpoint,
            'registration_endpoint': self.registration_endpoint,
            'revocation_endpoint': self.revocation_endpoint,
            'scopes_supported': self.scopes_supported,
            'response_types_supported': self.response_types_supported,
            'code_challenge_methods_supported': self.code_challenge_methods_supported,
            'token_endpoint_auth_methods_supported': self.token_endpoint_auth_methods_supported,
        }

    @property
    def supports_dynamic_registration(self) -> bool:
        """Check if server supports dynamic client registration."""
        return bool(self.registration_endpoint)

    @property
    def supports_pkce(self) -> bool:
        """Check if server supports PKCE (required by MCP spec)."""
        return 'S256' in self.code_challenge_methods_supported


@dataclass
class DynamicClientCredentials:
    """OAuth client credentials from registration or manual entry."""
    client_id: str
    client_secret: str = ''


@dataclass
class DynamicTokenResponse:
    """OAuth token response."""
    access_token: str
    token_type: str = 'Bearer'
    expires_in: Optional[int] = None
    refresh_token: str = ''
    scope: str = ''

    @classmethod
    def from_response(cls, data: dict) -> 'DynamicTokenResponse':
        """Create from token endpoint response."""
        return cls(
            access_token=data.get('access_token', ''),
            token_type=data.get('token_type', 'Bearer'),
            expires_in=data.get('expires_in'),
            refresh_token=data.get('refresh_token', ''),
            scope=data.get('scope', ''),
        )


class PKCEFlow:
    """Handles PKCE (Proof Key for Code Exchange) for OAuth 2.1.

    PKCE is REQUIRED by the MCP specification for all OAuth flows.
    """

    @staticmethod
    def generate_verifier(length: int = 64) -> str:
        """Generate cryptographically random code verifier."""
        return secrets.token_urlsafe(length)[:128]

    @staticmethod
    def generate_challenge(verifier: str) -> str:
        """Generate S256 code challenge from verifier."""
        digest = hashlib.sha256(verifier.encode('ascii')).digest()
        return base64.urlsafe_b64encode(digest).rstrip(b'=').decode('ascii')

    @staticmethod
    def generate_state() -> str:
        """Generate random state parameter for CSRF protection."""
        return secrets.token_urlsafe(32)

    @classmethod
    def build_authorization_url(
        cls,
        authorization_endpoint: str,
        client_id: str,
        redirect_uri: str,
        code_challenge: str,
        state: str,
        scopes: Optional[list] = None,
        resource: str = '',
    ) -> str:
        """Build the OAuth authorization URL with PKCE (`resource`: RFC 8707, sent unconditionally)."""
        params = {
            'response_type': 'code',
            'client_id': client_id,
            'redirect_uri': redirect_uri,
            'code_challenge': code_challenge,
            'code_challenge_method': 'S256',
            'state': state,
        }
        if scopes:
            params['scope'] = ' '.join(scopes)
        if resource:
            params['resource'] = resource
        return f"{authorization_endpoint}?{urlencode(params)}"


class DynamicOAuthDiscoveryService:
    """Discovers OAuth configuration from MCP servers dynamically.

    RFC 9728 locates the authorization server(s); RFC 8414 / OpenID
    Connect discovery fetches their endpoints (see `oauth_metadata.py`).
    """

    DEFAULT_TIMEOUT = 30.0

    def __init__(self, timeout: float = DEFAULT_TIMEOUT):
        self.timeout = timeout

    def _get_base_url(self, server_url: str) -> str:
        """Extract base URL (remove path components)."""
        parsed = urlparse(server_url)
        return f"{parsed.scheme}://{parsed.netloc}"

    async def discover(self, server_url: str) -> DynamicOAuthMetadata:
        """Discover OAuth metadata for the server protecting `server_url`.

        Follows RFC 9728 to the named authorization server(s) — which may
        live on a different origin — falling back to same-origin discovery.
        """
        prm, challenge_scope = await discover_protected_resource_metadata(server_url, timeout=self.timeout)
        base_url = self._get_base_url(server_url)
        issuers_to_try = list((prm or {}).get('authorization_servers') or []) or [base_url]

        for issuer in issuers_to_try:
            data = await discover_authorization_server_metadata(issuer, timeout=self.timeout)
            if data is None:
                continue
            metadata = DynamicOAuthMetadata.from_response(data)
            if challenge_scope:
                metadata.scopes_supported = challenge_scope.split()
            logger.info(f"OAuth discovery successful: {metadata.issuer}")
            return metadata

        logger.info(f"No authorization server metadata found for {server_url}, using fallback endpoints")
        return DynamicOAuthMetadata.with_defaults(base_url)

    async def register_client(
        self,
        registration_endpoint: str,
        redirect_uri: str,
        client_name: str = 'Sterna AI',
    ) -> DynamicClientCredentials:
        """Dynamically register with OAuth server (RFC 7591)."""
        payload = {
            'client_name': client_name,
            'redirect_uris': [redirect_uri],
            'grant_types': ['authorization_code', 'refresh_token'],
            'response_types': ['code'],
            'token_endpoint_auth_method': 'client_secret_basic',
        }

        logger.info(f"Registering OAuth client at {registration_endpoint}")

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    registration_endpoint,
                    json=payload,
                    headers={
                        'Content-Type': 'application/json',
                        'Accept': 'application/json',
                    },
                )

                if response.status_code in (200, 201):
                    data = response.json()
                    logger.info("OAuth client registration successful")
                    return DynamicClientCredentials(
                        client_id=data['client_id'],
                        client_secret=data.get('client_secret', ''),
                    )

                raise DynamicOAuthRegistrationError(
                    f"Client registration failed: HTTP {response.status_code} - {response.text}"
                )

        except httpx.RequestError as e:
            raise DynamicOAuthRegistrationError(f"Client registration request failed: {e}")


class DynamicOAuthTokenManager:
    """Manages OAuth tokens for dynamically discovered MCP servers."""

    DEFAULT_TIMEOUT = 60.0

    def __init__(self, timeout: float = DEFAULT_TIMEOUT):
        self.timeout = timeout

    async def exchange_code(
        self,
        token_endpoint: str,
        code: str,
        redirect_uri: str,
        client_id: str,
        client_secret: str = '',
        code_verifier: str = '',
        resource: str = '',
    ) -> DynamicTokenResponse:
        """Exchange authorization code for tokens (`resource`: RFC 8707, sent unconditionally)."""
        data = {
            'grant_type': 'authorization_code',
            'code': code,
            'redirect_uri': redirect_uri,
            'client_id': client_id,
        }

        if client_secret:
            data['client_secret'] = client_secret
        if code_verifier:
            data['code_verifier'] = code_verifier
        if resource:
            data['resource'] = resource

        logger.info(f"Exchanging authorization code at {token_endpoint}")

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    token_endpoint,
                    data=data,
                    headers={
                        'Content-Type': 'application/x-www-form-urlencoded',
                        'Accept': 'application/json',
                    },
                )

                if response.status_code == 200:
                    token_data = response.json()
                    logger.info("Token exchange successful")
                    return DynamicTokenResponse.from_response(token_data)

                error_data = response.json() if response.headers.get('content-type', '').startswith('application/json') else {}
                error_msg = error_data.get('error_description', error_data.get('error', response.text))
                raise DynamicOAuthTokenError(f"Token exchange failed: {error_msg}")

        except httpx.RequestError as e:
            raise DynamicOAuthTokenError(f"Token exchange request failed: {e}")

    async def refresh_token(
        self,
        token_endpoint: str,
        refresh_token: str,
        client_id: str,
        client_secret: str = '',
        resource: str = '',
    ) -> DynamicTokenResponse:
        """Refresh an expired access token."""
        data = {
            'grant_type': 'refresh_token',
            'refresh_token': refresh_token,
            'client_id': client_id,
        }

        if client_secret:
            data['client_secret'] = client_secret
        if resource:
            data['resource'] = resource

        logger.info(f"Refreshing token at {token_endpoint}")

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    token_endpoint,
                    data=data,
                    headers={
                        'Content-Type': 'application/x-www-form-urlencoded',
                        'Accept': 'application/json',
                    },
                )

                if response.status_code == 200:
                    token_data = response.json()
                    logger.info("Token refresh successful")
                    return DynamicTokenResponse.from_response(token_data)

                error_data = response.json() if response.headers.get('content-type', '').startswith('application/json') else {}
                error_msg = error_data.get('error_description', error_data.get('error', response.text))
                raise DynamicOAuthTokenError(f"Token refresh failed: {error_msg}")

        except httpx.RequestError as e:
            raise DynamicOAuthTokenError(f"Token refresh request failed: {e}")


class MCPDynamicOAuthFlow:
    """Orchestrates the complete dynamic OAuth flow for MCP servers."""

    def __init__(self):
        self.discovery = DynamicOAuthDiscoveryService()
        self.token_manager = DynamicOAuthTokenManager()

    def get_oauth_callback_url(self) -> str:
        """Get the OAuth callback URL for our application."""
        base_url = getattr(settings, 'SITE_URL', 'http://localhost:8000')
        return f"{base_url}/api/mcp/oauth/callback/"

    async def start_authorization(
        self,
        server: 'MCPServer',
        client_id: str = '',
        client_secret: str = '',
    ) -> dict:
        """Start the OAuth authorization flow for a server.

        Returns:
            dict with 'authorization_url' to redirect user to
        """
        # Ensure we have OAuth metadata
        if not server.oauth_metadata:
            metadata = await self.discovery.discover(server.remote_url)
            server.oauth_metadata = metadata.to_dict()
            await sync_to_async(server.save)(update_fields=['oauth_metadata'])
        else:
            metadata = DynamicOAuthMetadata.from_response(server.oauth_metadata)

        redirect_uri = self.get_oauth_callback_url()

        # Handle client credentials
        if client_id:
            server.oauth_client_id = client_id
            server.oauth_client_secret = client_secret
        elif not server.oauth_client_id:
            if metadata.supports_dynamic_registration:
                try:
                    creds = await self.discovery.register_client(
                        metadata.registration_endpoint,
                        redirect_uri,
                    )
                    server.oauth_client_id = creds.client_id
                    server.oauth_client_secret = creds.client_secret
                except DynamicOAuthRegistrationError as e:
                    raise DynamicOAuthFlowError(
                        f"Dynamic client registration failed: {e}. "
                        "Please provide client_id manually."
                    )
            else:
                raise DynamicOAuthFlowError(
                    "Server does not support dynamic registration. "
                    "Please provide OAuth client_id and client_secret."
                )

        # Generate PKCE values
        verifier = PKCEFlow.generate_verifier()
        challenge = PKCEFlow.generate_challenge(verifier)
        state = PKCEFlow.generate_state()

        # Store for callback verification
        server.oauth_pkce_verifier = verifier
        server.oauth_state = state
        # Use sync_to_async since we're in an async context
        await sync_to_async(server.save)(update_fields=[
            'oauth_client_id', 'oauth_client_secret',
            'oauth_pkce_verifier', 'oauth_state'
        ])

        # Build authorization URL
        auth_url = PKCEFlow.build_authorization_url(
            authorization_endpoint=metadata.authorization_endpoint,
            client_id=server.oauth_client_id,
            redirect_uri=redirect_uri,
            code_challenge=challenge,
            state=state,
            scopes=metadata.scopes_supported or None,
            resource=canonical_resource_uri(server.remote_url),
        )

        return {
            'authorization_url': auth_url,
            'state': state,
        }

    async def handle_callback(
        self,
        state: str,
        code: str = '',
        error: str = '',
        error_description: str = '',
    ) -> 'MCPServer':
        """Handle OAuth callback after user authorization."""
        from .models import MCPServer

        # Find server by state
        try:
            server = await sync_to_async(MCPServer.objects.get)(oauth_state=state)
        except MCPServer.DoesNotExist:
            raise DynamicOAuthCallbackError("Invalid state parameter - authorization may have expired")

        if error:
            # Check if this is a newly created server that was never authorized
            # (no access token and no tools discovered)
            has_tokens = bool(server.oauth_access_token)
            tools_count = await sync_to_async(lambda: server.tools.count())()
            is_new_server = not has_tokens and tools_count == 0

            if is_new_server:
                # Delete the server since user cancelled before ever authorizing
                server_name = server.name
                await sync_to_async(server.delete)()
                logger.info(f"Deleted unused server '{server_name}' after OAuth cancellation")
                raise DynamicOAuthCallbackError("Authorization cancelled")
            else:
                # Keep existing server, just clear the pending OAuth state
                server.oauth_state = ''
                await sync_to_async(server.save)(update_fields=['oauth_state'])
                raise DynamicOAuthCallbackError(f"Authorization denied: {error_description or error}")

        if not code:
            raise DynamicOAuthCallbackError("No authorization code received")

        # Exchange code for tokens
        metadata = DynamicOAuthMetadata.from_response(server.oauth_metadata)
        redirect_uri = self.get_oauth_callback_url()

        try:
            tokens = await self.token_manager.exchange_code(
                token_endpoint=metadata.token_endpoint,
                code=code,
                redirect_uri=redirect_uri,
                client_id=server.oauth_client_id,
                client_secret=server.oauth_client_secret,
                code_verifier=server.oauth_pkce_verifier,
                resource=canonical_resource_uri(server.remote_url),
            )
        except DynamicOAuthTokenError as e:
            server.oauth_state = ''
            server.oauth_pkce_verifier = ''
            await sync_to_async(server.save)(update_fields=['oauth_state', 'oauth_pkce_verifier'])
            raise DynamicOAuthCallbackError(f"Token exchange failed: {e}")

        # Store tokens
        scopes = tokens.scope.split() if tokens.scope else []
        await sync_to_async(server.store_oauth_tokens)(
            access_token=tokens.access_token,
            refresh_token=tokens.refresh_token,
            expires_in=tokens.expires_in,
            scopes=scopes,
        )

        # Mark as connected
        await sync_to_async(server.mark_connected)()
        return server

    async def refresh_server_token(self, server: 'MCPServer') -> bool:
        """Refresh OAuth token for a server."""
        if not server.oauth_refresh_token:
            logger.warning(f"No refresh token available for server {server.id}")
            return False

        metadata = DynamicOAuthMetadata.from_response(server.oauth_metadata)

        try:
            tokens = await self.token_manager.refresh_token(
                token_endpoint=metadata.token_endpoint,
                refresh_token=server.oauth_refresh_token,
                client_id=server.oauth_client_id,
                client_secret=server.oauth_client_secret,
                resource=canonical_resource_uri(server.remote_url),
            )

            await sync_to_async(server.store_oauth_tokens)(
                access_token=tokens.access_token,
                refresh_token=tokens.refresh_token or server.oauth_refresh_token,
                expires_in=tokens.expires_in,
            )

            logger.info(f"Token refresh successful for server {server.id}")
            return True

        except DynamicOAuthTokenError as e:
            logger.error(f"Token refresh failed for server {server.id}: {e}")
            return False


# =============================================================================
# Dynamic OAuth Exceptions
# =============================================================================

class DynamicOAuthError(Exception):
    """Base exception for dynamic OAuth errors."""
    pass


class DynamicOAuthRegistrationError(DynamicOAuthError):
    """Error during dynamic client registration."""
    pass


class DynamicOAuthTokenError(DynamicOAuthError):
    """Error during token exchange or refresh."""
    pass


class DynamicOAuthFlowError(DynamicOAuthError):
    """Error during OAuth flow."""
    pass


class DynamicOAuthCallbackError(DynamicOAuthError):
    """Error handling OAuth callback."""
    pass
