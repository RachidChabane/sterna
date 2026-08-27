"""Serializers for MCP models."""

from rest_framework import serializers

from .models import (
    MCPDiscoverySearch,
    MCPServer,
    MCPTool,
    MCPToolApproval,
    MCPToolExecution,
)


class MCPServerSerializer(serializers.ModelSerializer):
    """Serializer for MCPServer model.

    SECURITY NOTE: auth_config and env_vars are intentionally EXCLUDED from serialization
    to prevent OAuth tokens and secrets from being exposed in API responses.
    """

    connection_status = serializers.SerializerMethodField()
    oauth_connection_status = serializers.SerializerMethodField()
    tools_count = serializers.SerializerMethodField()
    tools = serializers.SerializerMethodField()
    has_auth = serializers.SerializerMethodField()
    has_env_vars = serializers.SerializerMethodField()
    connection_id = serializers.SerializerMethodField()
    env_var_keys = serializers.SerializerMethodField()
    server_type = serializers.SerializerMethodField()

    class Meta:
        model = MCPServer
        fields = [
            "id",
            "name",
            "description",
            "icon_url",
            "is_preconfigured",
            "is_official",
            "category",
            "transport_type",
            "server_type",  # Computed: 'local', 'remote_http', 'remote_websocket'
            "url",
            "npm_package",
            "command",
            "working_directory",
            "allowed_domains",
            # Remote server fields
            "remote_url",
            "auth_type",
            "auth_header_name",
            # SECURITY: auth_config and env_vars EXCLUDED - contain secrets
            "has_auth",  # Boolean indicator only
            "has_env_vars",  # Boolean indicator only
            "env_var_keys",  # Only show keys, not values
            "connection_id",  # Connection ID only (safe to expose)
            "is_active",
            "connection_healthy",
            "last_connected",
            "last_health_check",
            "last_error",
            "connection_status",
            "oauth_connection_status",
            "tools_count",
            "tools",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "server_type",
            "connection_healthy",
            "last_connected",
            "last_health_check",
            "last_error",
            "connection_status",
            "oauth_connection_status",
            "tools_count",
            "tools",
            "has_auth",
            "has_env_vars",
            "env_var_keys",
            "connection_id",
            "created_at",
            "updated_at",
        ]

    def get_oauth_connection_status(self, obj):
        """Return OAuth connection status from the model property."""
        return obj.oauth_connection_status

    def get_server_type(self, obj):
        """Return the detected server type."""
        return obj.server_type

    def get_has_auth(self, obj):
        """Return whether server has auth configured (without exposing tokens)."""
        return bool(obj.auth_config)

    def get_has_env_vars(self, obj):
        """Return whether server has environment variables configured."""
        return bool(obj.env_vars)

    def get_env_var_keys(self, obj):
        """Return list of environment variable keys (without values for security)."""
        if obj.env_vars and isinstance(obj.env_vars, dict):
            return list(obj.env_vars.keys())
        return []

    def get_connection_id(self, obj):
        """Get connection ID from auth_config without exposing OAuth tokens."""
        if obj.auth_config and isinstance(obj.auth_config, dict):
            return obj.auth_config.get('connection_id')
        return None

    def get_connection_status(self, obj):
        """Get connection status with freshness check.

        Returns:
            - "inactive": Server is disabled
            - "connected": Recently verified as healthy
            - "stale": Connected but not verified recently
            - "error": Last health check failed
            - "never_connected": Never successfully connected
        """
        if not obj.is_active:
            return "inactive"

        # Check if we have a recent health check
        if obj.last_health_check:
            is_fresh = obj.is_connection_fresh(threshold_minutes=5)

            if is_fresh and obj.connection_healthy:
                return "connected"
            elif is_fresh and not obj.connection_healthy:
                return "error"
            elif obj.last_connected:
                # Status is stale - was connected before but not checked recently
                return "stale"

        # No health check data
        if obj.last_connected:
            return "stale"  # Was connected but never health-checked
        if obj.last_error:
            return "error"

        return "never_connected"

    def get_tools_count(self, obj):
        """Get number of tools discovered."""
        # For user servers connected to a preconfigured server, get tools from preconfigured
        tools_server = self._get_tools_server(obj)
        return tools_server.tools.count()

    def get_tools(self, obj):
        """Get tools for this server."""
        # For user servers connected to a preconfigured server, get tools from preconfigured
        tools_server = self._get_tools_server(obj)
        tools_data = []
        for tool in tools_server.tools.all():
            tools_data.append({
                'id': tool.id,
                'name': tool.name,
                'description': tool.description,
            })
        return tools_data

    def _get_tools_server(self, obj):
        """Get the server that holds tools (preconfigured if connected to one)."""
        if obj.is_preconfigured:
            return obj

        # For user servers, find the preconfigured server with matching URL/package
        from .models import MCPServer
        preconfigured = None

        if obj.remote_url:
            preconfigured = MCPServer.objects.filter(
                remote_url=obj.remote_url,
                is_preconfigured=True,
            ).first()
        elif obj.npm_package:
            preconfigured = MCPServer.objects.filter(
                npm_package=obj.npm_package,
                is_preconfigured=True,
            ).first()

        return preconfigured if preconfigured else obj

    def validate_npm_package(self, value):
        """Validate npm package name format."""
        if not value:
            return value

        import re
        # Basic npm package name validation (allows scoped packages)
        pattern = r'^(@[a-z0-9-~][a-z0-9-._~]*/)?[a-z0-9-~][a-z0-9-._~]*$'
        if not re.match(pattern, value, re.IGNORECASE):
            raise serializers.ValidationError("Invalid NPM package name format")

        return value

    def validate_allowed_domains(self, value):
        """Validate allowed_domains is a list of strings."""
        if not value:
            return value

        if not isinstance(value, list):
            raise serializers.ValidationError("allowed_domains must be a list")

        for domain in value:
            if not isinstance(domain, str):
                raise serializers.ValidationError("All domains must be strings")

        return value

    def validate_remote_url(self, value):
        """Validate remote URL format."""
        if not value:
            return value

        # Must be http or https for remote HTTP servers
        if not value.startswith(('http://', 'https://')):
            raise serializers.ValidationError(
                "Remote URL must start with http:// or https://"
            )

        return value

    def validate(self, data):
        """Validate server configuration.

        Server can be one of:
        - Local (npm_package set) - runs in Docker sandbox
        - Remote HTTP (remote_url set with http/https) - connects to external server
        - Remote WebSocket (url set with ws/wss) - connects to external WebSocket
        """
        transport_type = data.get("transport_type", self.instance.transport_type if self.instance else None)
        remote_url = data.get("remote_url") or (self.instance and getattr(self.instance, 'remote_url', None))
        npm_package = data.get("npm_package") or (self.instance and self.instance.npm_package)
        url = data.get("url") or (self.instance and self.instance.url)

        # Check for conflicting configurations
        if npm_package and remote_url:
            raise serializers.ValidationError({
                "npm_package": "Cannot specify both npm_package (local) and remote_url (remote)"
            })

        # Validate based on transport type
        if transport_type == MCPServer.TransportType.WEBSOCKET:
            if not url:
                raise serializers.ValidationError({
                    "url": "URL is required for WebSocket transport"
                })
        elif transport_type == MCPServer.TransportType.HTTP:
            if not remote_url:
                raise serializers.ValidationError({
                    "remote_url": "Remote URL is required for HTTP transport"
                })
        elif transport_type in (MCPServer.TransportType.STDIO, MCPServer.TransportType.SANDBOXED):
            # Either npm_package or command is required
            has_cmd = data.get("command") or (self.instance and self.instance.command)
            if not npm_package and not has_cmd:
                raise serializers.ValidationError({
                    "npm_package": "NPM package or command is required for local/stdio transport"
                })
        else:
            # Auto-detect based on provided fields
            if not npm_package and not remote_url and not url:
                raise serializers.ValidationError(
                    "Must provide either npm_package (for local server) or "
                    "remote_url (for remote HTTP) or url (for WebSocket)"
                )

        return data

    def create(self, validated_data):
        """Create MCPServer with current user."""
        validated_data["user"] = self.context["request"].user
        return super().create(validated_data)


class MCPServerCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating custom MCP servers.

    This serializer is used for the public API where users create their own servers.
    Supports both local (npm package) and remote (URL) server types.

    It accepts env_vars and auth_config as input but never returns them in responses.
    """

    env_vars = serializers.JSONField(required=False, default=dict, write_only=True)
    auth_config = serializers.JSONField(required=False, default=dict, write_only=True)

    class Meta:
        model = MCPServer
        fields = [
            "id",
            "name",
            "description",
            "icon_url",
            "icon_invert_in_dark_mode",
            "transport_type",
            # Local server fields
            "npm_package",
            "env_vars",
            "allowed_domains",
            # Remote server fields
            "remote_url",
            "auth_type",
            "auth_header_name",
            "auth_config",  # Write-only, for API keys/tokens
            # Legacy WebSocket
            "url",
            # Status
            "is_active",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]

    def validate_env_vars(self, value):
        """Validate env_vars is a dict of strings."""
        if not value:
            return {}

        if not isinstance(value, dict):
            raise serializers.ValidationError("env_vars must be an object")

        for key, val in value.items():
            if not isinstance(key, str):
                raise serializers.ValidationError("env_vars keys must be strings")
            if not isinstance(val, str):
                raise serializers.ValidationError("env_vars values must be strings")

        return value

    def validate_auth_config(self, value):
        """Validate auth_config structure."""
        if not value:
            return {}

        if not isinstance(value, dict):
            raise serializers.ValidationError("auth_config must be an object")

        return value

    def validate_npm_package(self, value):
        """Validate npm package name format."""
        if not value:
            return value

        import re
        # Basic npm package name validation (allows scoped packages)
        pattern = r'^(@[a-z0-9-~][a-z0-9-._~]*/)?[a-z0-9-~][a-z0-9-._~]*$'
        if not re.match(pattern, value, re.IGNORECASE):
            raise serializers.ValidationError("Invalid NPM package name format")

        return value

    def validate_remote_url(self, value):
        """Validate remote URL format."""
        if not value:
            return value

        if not value.startswith(('http://', 'https://')):
            raise serializers.ValidationError(
                "Remote URL must start with http:// or https://"
            )

        return value

    def validate(self, data):
        """Validate server configuration.

        Auto-detects server type based on provided fields:
        - npm_package → local sandboxed server
        - remote_url → remote HTTP server
        - url (ws/wss) → remote WebSocket server
        """
        npm_package = data.get("npm_package")
        remote_url = data.get("remote_url")
        url = data.get("url")

        # Check for conflicting configurations
        if npm_package and remote_url:
            raise serializers.ValidationError({
                "npm_package": "Cannot specify both npm_package (local) and remote_url (remote)"
            })

        # Auto-set transport type based on provided fields
        if npm_package:
            data["transport_type"] = MCPServer.TransportType.SANDBOXED
        elif remote_url:
            data["transport_type"] = MCPServer.TransportType.HTTP
        elif url:
            data["transport_type"] = MCPServer.TransportType.WEBSOCKET
        else:
            raise serializers.ValidationError(
                "Must provide either npm_package (for local server), "
                "remote_url (for remote HTTP), or url (for WebSocket)"
            )

        return data

    def create(self, validated_data):
        """Create MCPServer with current user, preventing duplicates."""
        user = self.context["request"].user
        validated_data["user"] = user

        # Check for duplicate connections
        npm_package = validated_data.get("npm_package")
        remote_url = validated_data.get("remote_url")
        url = validated_data.get("url")

        existing_query = MCPServer.objects.filter(user=user)

        if npm_package:
            existing = existing_query.filter(npm_package=npm_package).first()
            if existing:
                raise serializers.ValidationError({
                    "npm_package": "You are already connected to a server with this package. Check 'My Servers'."
                })

        if remote_url:
            existing = existing_query.filter(remote_url=remote_url).first()
            if existing:
                raise serializers.ValidationError({
                    "remote_url": "You are already connected to this server. Check 'My Servers'."
                })

        if url:
            existing = existing_query.filter(url=url).first()
            if existing:
                raise serializers.ValidationError({
                    "url": "You are already connected to this server. Check 'My Servers'."
                })

        return super().create(validated_data)

    def to_representation(self, instance):
        """Use MCPServerSerializer for output."""
        return MCPServerSerializer(instance, context=self.context).data


class MCPServerMinimalSerializer(serializers.ModelSerializer):
    """Minimal serializer for MCPServer (for nested representations)."""

    class Meta:
        model = MCPServer
        fields = ["id", "name", "transport_type", "is_active"]


class MCPServerPreconfiguredSerializer(serializers.ModelSerializer):
    """Serializer for preconfigured MCP servers.

    Shows only public information about preconfigured servers
    that are available for users to connect to.

    Includes tools list so users can see available capabilities
    before connecting.
    """

    server_type = serializers.SerializerMethodField()
    requires_auth = serializers.SerializerMethodField()
    tools_count = serializers.SerializerMethodField()
    tools = serializers.SerializerMethodField()
    category_display = serializers.SerializerMethodField()

    class Meta:
        model = MCPServer
        fields = [
            "id",
            "name",
            "description",
            "icon_url",
            "icon_invert_in_dark_mode",
            "is_official",
            "docs_url",
            "category",
            "category_display",
            "transport_type",
            "server_type",
            "requires_auth",
            "auth_type",
            "npm_package",
            "remote_url",
            "tools_count",
            "tools",
        ]

    def get_server_type(self, obj):
        """Return the detected server type."""
        return obj.server_type

    def get_requires_auth(self, obj):
        """Check if server requires user authentication/credentials."""
        # OAuth servers require user authorization
        if obj.auth_type == MCPServer.AuthType.OAUTH:
            return True
        # NPM servers with env vars need user to provide credentials
        if obj.npm_package and obj.env_vars:
            return True
        # Remote servers with API key/bearer require credentials
        if obj.auth_type in (MCPServer.AuthType.API_KEY, MCPServer.AuthType.BEARER):
            return True
        return False

    def get_tools_count(self, obj):
        """Get number of tools available."""
        return obj.tools.count()

    def get_tools(self, obj):
        """Get list of tools with minimal info for display."""
        return [
            {
                "id": str(tool.id),
                "name": tool.name,
                "description": tool.description,
            }
            for tool in obj.tools.all()[:50]  # Limit to 50 for performance
        ]

    def get_category_display(self, obj):
        """Get human-readable category name."""
        return obj.get_category_display()


class MCPToolSerializer(serializers.ModelSerializer):
    """Serializer for MCPTool model."""

    server = MCPServerMinimalSerializer(read_only=True)
    server_id = serializers.PrimaryKeyRelatedField(
        queryset=MCPServer.objects.all(),
        source="server",
        write_only=True,
    )

    class Meta:
        model = MCPTool
        fields = [
            "id",
            "server",
            "server_id",
            "name",
            "description",
            "input_schema",
            "metadata",
            "discovered_at",
            "last_refreshed",
        ]
        read_only_fields = [
            "id",
            "discovered_at",
            "last_refreshed",
        ]


class MCPToolMinimalSerializer(serializers.ModelSerializer):
    """Minimal serializer for MCPTool (for nested representations)."""

    server_name = serializers.CharField(source="server.name", read_only=True)
    server_icon_url = serializers.SerializerMethodField()

    class Meta:
        model = MCPTool
        fields = ["id", "name", "description", "server_name", "server_icon_url"]

    def get_server_icon_url(self, obj):
        """Get the server icon URL."""
        return obj.server.icon_url


class MCPToolApprovalSerializer(serializers.ModelSerializer):
    """Serializer for MCPToolApproval model."""

    tool = MCPToolMinimalSerializer(read_only=True)
    tool_id = serializers.PrimaryKeyRelatedField(
        queryset=MCPTool.objects.all(),
        source="tool",
        write_only=True,
    )
    # DRF's SerializerMetaclass pops declared Field attributes out of the
    # class namespace before the class object is created (see
    # rest_framework.serializers.SerializerMetaclass._get_declared_fields),
    # so this never actually shadows BaseSerializer.is_valid() at runtime —
    # only the stub-derived static type sees a collision.
    is_valid = serializers.SerializerMethodField()  # type: ignore[assignment]

    class Meta:
        model = MCPToolApproval
        fields = [
            "id",
            "tool",
            "tool_id",
            "session_id",
            "proposed_arguments",
            "status",
            "scope",
            "requested_at",
            "decided_at",
            "expires_at",
            "is_valid",
        ]
        read_only_fields = [
            "id",
            "requested_at",
            "decided_at",
            "is_valid",
        ]

    def get_is_valid(self, obj):
        """Check if approval is still valid."""
        return obj.is_valid()

    def create(self, validated_data):
        """Create approval with current user."""
        validated_data["user"] = self.context["request"].user
        return super().create(validated_data)


class MCPToolExecutionSerializer(serializers.ModelSerializer):
    """Serializer for MCPToolExecution model."""

    tool = MCPToolMinimalSerializer(read_only=True)
    tool_id = serializers.PrimaryKeyRelatedField(
        queryset=MCPTool.objects.all(),
        source="tool",
        write_only=True,
        required=False,
    )

    class Meta:
        model = MCPToolExecution
        fields = [
            "id",
            "tool",
            "tool_id",
            "approval",
            "session_id",
            "arguments",
            "status",
            "result",
            "error_message",
            "started_at",
            "completed_at",
            "duration_ms",
        ]
        read_only_fields = [
            "id",
            "status",
            "result",
            "error_message",
            "started_at",
            "completed_at",
            "duration_ms",
        ]


# Request/Response serializers for actions

class DiscoverToolsRequestSerializer(serializers.Serializer):
    """Request serializer for discovering tools."""

    force_refresh = serializers.BooleanField(default=False)


class TestConnectionRequestSerializer(serializers.Serializer):
    """Request serializer for testing connection."""

    pass  # No parameters needed


class CallToolRequestSerializer(serializers.Serializer):
    """Request serializer for calling a tool."""

    arguments = serializers.JSONField()
    session_id = serializers.CharField(required=False, allow_blank=True)


class ApproveToolRequestSerializer(serializers.Serializer):
    """Request serializer for approving a tool."""

    scope = serializers.ChoiceField(
        choices=MCPToolApproval.ApprovalScope.choices,
        default=MCPToolApproval.ApprovalScope.ONCE,
    )


class RejectToolRequestSerializer(serializers.Serializer):
    """Request serializer for rejecting a tool."""

    pass  # No parameters needed


class MCPDiscoverySearchSerializer(serializers.ModelSerializer):
    """Serializer for MCPDiscoverySearch model."""

    total_results = serializers.IntegerField(read_only=True)

    class Meta:
        model = MCPDiscoverySearch
        fields = [
            "id",
            "query",
            "preconfigured_results",
            "external_results",
            "total_results",
            "created_at",
        ]
        read_only_fields = ["id", "created_at", "total_results"]

    def create(self, validated_data):
        """Create search entry with current user."""
        validated_data["user"] = self.context["request"].user
        return super().create(validated_data)
