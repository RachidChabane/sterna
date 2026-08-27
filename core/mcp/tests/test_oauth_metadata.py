"""Unit tests for the pure helpers in mcp/oauth_metadata.py.

Integration-style coverage of the full discovery flow (PRM →
authorization server, well-known fallbacks, issuer validation) lives in
test_oauth_flow.py alongside the rest of the OAuth flow tests.
"""

from mcp.oauth_metadata import (
    _authorization_server_metadata_urls,
    _protected_resource_well_known_urls,
    canonical_resource_uri,
    parse_www_authenticate,
)


def test_parse_www_authenticate_extracts_resource_metadata_and_scope():
    header = (
        'Bearer resource_metadata="https://mcp.example.com/.well-known/'
        'oauth-protected-resource", scope="files:read files:write"'
    )
    params = parse_www_authenticate(header)
    assert params["resource_metadata"] == "https://mcp.example.com/.well-known/oauth-protected-resource"
    assert params["scope"] == "files:read files:write"


def test_parse_www_authenticate_ignores_non_bearer_schemes():
    assert parse_www_authenticate('Basic realm="example"') == {}


def test_parse_www_authenticate_handles_missing_header():
    assert parse_www_authenticate("") == {}


def test_canonical_resource_uri_lowercases_and_strips_trailing_slash():
    assert canonical_resource_uri("HTTPS://MCP.Example.COM/Path/") == "https://mcp.example.com/Path"


def test_canonical_resource_uri_leaves_pathless_url_unchanged():
    assert canonical_resource_uri("https://mcp.example.com") == "https://mcp.example.com"


def test_protected_resource_well_known_urls_tries_path_before_root():
    urls = _protected_resource_well_known_urls("https://mcp.example.com/public/mcp")
    assert urls == [
        "https://mcp.example.com/.well-known/oauth-protected-resource/public/mcp",
        "https://mcp.example.com/.well-known/oauth-protected-resource",
    ]


def test_protected_resource_well_known_urls_root_only_when_no_path():
    urls = _protected_resource_well_known_urls("https://mcp.example.com")
    assert urls == ["https://mcp.example.com/.well-known/oauth-protected-resource"]


def test_authorization_server_metadata_urls_priority_order_with_path():
    """MCP spec order for an issuer with a path: RFC 8414 path-insertion,
    then OIDC path-insertion, then OIDC path-appending."""
    urls = _authorization_server_metadata_urls("https://auth.example.com/tenant1")
    assert urls == [
        "https://auth.example.com/.well-known/oauth-authorization-server/tenant1",
        "https://auth.example.com/.well-known/openid-configuration/tenant1",
        "https://auth.example.com/tenant1/.well-known/openid-configuration",
    ]


def test_authorization_server_metadata_urls_priority_order_without_path():
    urls = _authorization_server_metadata_urls("https://auth.example.com")
    assert urls == [
        "https://auth.example.com/.well-known/oauth-authorization-server",
        "https://auth.example.com/.well-known/openid-configuration",
    ]
