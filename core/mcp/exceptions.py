"""Custom exceptions for MCP integration."""

from typing import Optional


class MCPError(Exception):
    """Base exception for all MCP-related errors."""

    pass


class MCPConnectionError(MCPError):
    """Raised when connection to MCP server fails."""

    pass


class MCPTimeoutError(MCPError):
    """Raised when an MCP operation times out."""

    pass


class MCPToolNotFoundError(MCPError):
    """Raised when a requested tool is not available."""

    pass


class MCPInvalidParametersError(MCPError):
    """Raised when tool parameters are invalid."""

    pass


class MCPServerError(MCPError):
    """Raised when the MCP server returns an error."""

    def __init__(self, message: str, error_code: Optional[str] = None):
        """Initialize server error with optional error code."""
        super().__init__(message)
        self.error_code = error_code


class MCPProtocolError(MCPError):
    """Raised when there's a protocol-level error."""

    pass


class MCPUnsupportedProtocolVersionError(MCPConnectionError):
    """Raised when client and server share no common protocol version."""

    pass


class MCPAuthenticationError(MCPError):
    """Raised when authentication fails."""

    pass
