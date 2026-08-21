"""MCP protocol definitions and message types.

Based on the Model Context Protocol specification.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional


class MCPMessageType(str, Enum):
    """MCP message types."""

    # Handshake
    INITIALIZE = "initialize"
    INITIALIZED = "initialized"

    # Discovery
    LIST_TOOLS = "tools/list"
    LIST_RESOURCES = "resources/list"
    LIST_PROMPTS = "prompts/list"

    # Execution
    CALL_TOOL = "tools/call"

    # Resources
    READ_RESOURCE = "resources/read"

    # Prompts
    GET_PROMPT = "prompts/get"

    # Notifications
    NOTIFICATION = "notification"

    # Errors
    ERROR = "error"


@dataclass
class MCPRequest:
    """Base MCP request message."""

    jsonrpc: str = "2.0"
    id: Optional[str] = None
    method: str = ""
    params: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert request to dictionary."""
        result = {
            "jsonrpc": self.jsonrpc,
            "method": self.method,
        }
        if self.id is not None:
            result["id"] = self.id
        if self.params is not None:
            result["params"] = self.params
        return result


@dataclass
class MCPResponse:
    """Base MCP response message."""

    jsonrpc: str
    id: str
    result: Optional[Dict[str, Any]] = None
    error: Optional[Dict[str, Any]] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MCPResponse":
        """Create response from dictionary."""
        return cls(
            jsonrpc=data.get("jsonrpc", "2.0"),
            id=data.get("id", ""),
            result=data.get("result"),
            error=data.get("error"),
        )

    def is_error(self) -> bool:
        """Check if response is an error."""
        return self.error is not None


@dataclass
class MCPToolDefinition:
    """MCP tool definition."""

    name: str
    description: str
    inputSchema: Dict[str, Any]
    metadata: Optional[Dict[str, Any]] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MCPToolDefinition":
        """Create tool definition from dictionary."""
        return cls(
            name=data["name"],
            description=data["description"],
            inputSchema=data["inputSchema"],
            metadata=data.get("metadata"),
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        result = {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.inputSchema,
        }
        if self.metadata:
            result["metadata"] = self.metadata
        return result


@dataclass
class MCPResourceDefinition:
    """MCP resource definition."""

    uri: str
    name: str
    description: Optional[str] = None
    mimeType: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MCPResourceDefinition":
        """Create resource definition from dictionary."""
        return cls(
            uri=data["uri"],
            name=data["name"],
            description=data.get("description"),
            mimeType=data.get("mimeType"),
        )


@dataclass
class MCPPromptDefinition:
    """MCP prompt definition."""

    name: str
    description: Optional[str] = None
    arguments: Optional[List[Dict[str, Any]]] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MCPPromptDefinition":
        """Create prompt definition from dictionary."""
        return cls(
            name=data["name"],
            description=data.get("description"),
            arguments=data.get("arguments"),
        )


@dataclass
class MCPToolCallResult:
    """Result of a tool call."""

    content: List[Dict[str, Any]]
    isError: bool = False

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MCPToolCallResult":
        """Create tool call result from dictionary."""
        return cls(
            content=data.get("content", []),
            isError=data.get("isError", False),
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "content": self.content,
            "isError": self.isError,
        }
