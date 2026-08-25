/**
 * API integration for MCP (Model Context Protocol)
 */

import apiClient from './client'

/**
 * Get the full backend API URL for browser redirects
 * Used for redirects (window.location.href) which don't go through Vite proxy
 *
 * IMPORTANT: This returns the PUBLIC URL accessible from the browser,
 * not the internal Docker network URL (which is only for Vite proxy).
 */
const getBackendUrl = (): string => {
  // In production, backend is at the same origin, so we can use relative URLs
  if (import.meta.env.PROD) {
    return ''
  }
  // In development, browser redirects go through API Gateway
  // Uses VITE_BACKEND_URL or falls back to API Gateway port
  return import.meta.env.VITE_BACKEND_URL || 'http://localhost:8080'
}

// ============================================================================
// Types
// ============================================================================

export type MCPServerCategory = 'productivity' | 'communication' | 'developer' | 'automation' | 'cloud' | 'data' | 'crm' | 'finance' | 'ai' | 'design' | 'ecommerce' | 'utilities'

export interface MCPServer {
  id: string
  name: string
  description?: string
  icon_url?: string
  is_preconfigured?: boolean
  category?: MCPServerCategory
  transport_type: 'websocket' | 'stdio' | 'http' | 'sandboxed'
  server_type: 'local' | 'remote_http' | 'remote_websocket' | 'unknown'  // Computed field

  // Legacy WebSocket
  url?: string

  // Local server fields
  npm_package?: string  // NPM package name for sandboxed execution
  command?: string
  working_directory?: string
  allowed_domains?: string[]  // Custom domains for network egress whitelist

  // Remote HTTP server fields
  remote_url?: string  // HTTP endpoint for remote servers
  auth_type?: 'none' | 'api_key' | 'bearer' | 'oauth'
  auth_header_name?: string

  // Auth & env vars (values never exposed)
  auth_config?: Record<string, unknown>
  connection_id?: string  // Internal connection ID (from auth_config)
  has_auth?: boolean  // Whether server has auth configured (without exposing tokens)
  has_env_vars?: boolean  // Whether server has env vars configured
  env_var_keys?: string[]  // List of env var keys (without values)

  // OAuth status (for dynamic OAuth servers)
  oauth_connection_status?: 'not_configured' | 'pending' | 'connected' | 'expired'
  oauth_scopes?: string[]
  oauth_token_expires_at?: string

  // Status
  is_active: boolean
  connection_status?: 'inactive' | 'connected' | 'stale' | 'error' | 'never_connected'
  last_error?: string
  tools_count?: number
  tools?: MCPToolMinimal[]

  created_at: string
  updated_at: string
}

export interface MCPToolMinimal {
  id: string
  name: string
  description: string
}

interface MCPToolServer {
  id: string
  name: string
  transport_type: 'websocket' | 'stdio'
  is_active: boolean
}

export interface MCPTool {
  id: string
  server: MCPToolServer  // server object (not just ID)
  name: string
  description: string
  input_schema: Record<string, unknown>
  cached_at: string
}

export interface MCPToolApproval {
  id: string
  tool: string  // tool ID
  tool_name?: string
  session_id?: string
  proposed_arguments: Record<string, unknown>
  status: 'pending' | 'approved' | 'rejected'
  scope: 'once' | 'session' | 'permanent'
  approved_at?: string
  rejected_at?: string
  expires_at?: string
  created_at: string
}

export interface MCPToolExecution {
  id: string
  tool: string  // tool ID
  tool_name?: string
  approval?: string  // approval ID
  session_id?: string
  arguments: Record<string, unknown>
  result?: Record<string, unknown>
  error_message?: string
  status: 'pending' | 'running' | 'success' | 'error'
  started_at?: string
  completed_at?: string
  duration_ms?: number
  created_at: string
}

export interface MCPServerCreateRequest {
  name: string
  description?: string

  // Icon (copied from preconfigured server when connecting)
  icon_url?: string
  icon_invert_in_dark_mode?: boolean

  // Transport type (auto-detected based on other fields if not provided)
  transport_type?: 'websocket' | 'stdio' | 'http' | 'sandboxed'

  // Local server fields
  npm_package?: string  // NPM package name for sandboxed execution
  env_vars?: Record<string, string>  // Environment variables (API keys, tokens)
  allowed_domains?: string[]  // Custom domains for network egress whitelist

  // Remote HTTP server fields
  remote_url?: string  // HTTP endpoint for remote servers
  auth_type?: 'none' | 'api_key' | 'bearer' | 'oauth'
  auth_header_name?: string
  auth_config?: Record<string, unknown>  // Contains 'token' for auth

  // Legacy WebSocket
  url?: string

  // Legacy fields
  command?: string  // Legacy - use npm_package instead
  working_directory?: string

  is_active?: boolean
}

// Response from starting a server in sandbox
export interface MCPSandboxStartResponse {
  status: 'success' | 'error'
  message: string
  container_id?: string
  container_name?: string
}

export interface MCPServersResponse {
  results: MCPServer[]
  count: number
}

export interface MCPPreconfiguredServer {
  id: string
  name: string
  description: string
  icon_url?: string
  icon_invert_in_dark_mode?: boolean
  is_official?: boolean  // True = official from service provider, false = community/unofficial
  docs_url?: string  // URL to documentation or source code
  category: MCPServerCategory
  category_display: string
  transport_type: 'websocket' | 'stdio' | 'http' | 'sandboxed'
  server_type: 'local' | 'remote_http' | 'remote_websocket' | 'unknown'
  requires_auth: boolean
  auth_type: 'none' | 'api_key' | 'bearer' | 'oauth'
  npm_package?: string
  remote_url?: string
  tools_count: number
  tools?: MCPToolMinimal[]  // Available tools (populated when user connected)
}

export interface MCPPreconfiguredServersResponse {
  results: MCPPreconfiguredServer[]
  count: number
  next?: string | null
  previous?: string | null
}

export interface MCPToolsResponse {
  results: MCPTool[]
  count: number
}

export interface MCPApprovalsResponse {
  results: MCPToolApproval[]
  count: number
}

export interface MCPExecutionsResponse {
  results: MCPToolExecution[]
  count: number
}

interface MCPConfigRequirement {
  name: string
  label: string
  description: string
  required: boolean
  secret: boolean
  example?: string | null
  docs_url?: string | null
}

export interface MCPConfigHelpResponse {
  server_name: string
  env_vars: MCPConfigRequirement[]
  auth_info?: string | null
  setup_steps: string[]
  docs_url?: string | null
  allowed_domains: string[]
  auth_type?: 'none' | 'api_key' | 'bearer' | 'oauth' | null  // Detected auth type
  compatibility_warning?: string | null  // Warning if server may not work in cloud environment
}

export interface MCPDiscoveredServer {
  name: string
  description: string
  npm_package?: string | null
  remote_url?: string | null
  github_url?: string | null
  server_type: 'local' | 'remote'
  auth_type: 'none' | 'api_key' | 'bearer' | 'oauth'
  confidence: number
  source_url?: string | null
  // For preconfigured servers
  preconfigured_id?: string | null
  icon_url?: string | null
  icon_invert_in_dark_mode?: boolean
}

export interface MCPAIDiscoverResponse {
  query: string
  preconfigured: MCPDiscoveredServer[]
  external: MCPDiscoveredServer[]
  preconfigured_count: number
  external_count: number
}

export interface MCPDiscoveryHistoryEntry {
  id: string
  query: string
  preconfigured_results: MCPDiscoveredServer[]
  external_results: MCPDiscoveredServer[]
  total_results: number
  created_at: string
}

// ============================================================================
// API Functions
// ============================================================================

export const mcpApi = {
  // ========== Servers ==========

  /**
   * List all MCP servers for the current user
   */
  listServers: (params?: { custom_only?: boolean; oauth_only?: boolean }) =>
    apiClient.get<MCPServersResponse>('/mcp/servers/', { params }),

  /**
   * List only custom (npm-based) MCP servers
   */
  listCustomServers: () =>
    apiClient.get<MCPServersResponse>('/mcp/servers/', { params: { custom_only: 'true' } }),

  /**
   * List only OAuth-connected MCP servers
   */
  listOAuthServers: () =>
    apiClient.get<MCPServersResponse>('/mcp/servers/', { params: { oauth_only: 'true' } }),

  /**
   * List preconfigured MCP servers available to all users
   */
  listPreconfiguredServers: (params?: { page?: number; page_size?: number; search?: string; category?: string }) =>
    apiClient.get<MCPPreconfiguredServersResponse>('/mcp/servers/preconfigured/', { params }),

  /**
   * Get a specific MCP server by ID
   */
  getServer: (serverId: string) =>
    apiClient.get<MCPServer>(`/mcp/servers/${serverId}/`),

  /**
   * Create a new MCP server
   */
  createServer: (data: MCPServerCreateRequest) =>
    apiClient.post<MCPServer>('/mcp/servers/', data),

  /**
   * Update an existing MCP server
   */
  updateServer: (serverId: string, data: Partial<MCPServerCreateRequest>) =>
    apiClient.patch<MCPServer>(`/mcp/servers/${serverId}/`, data),

  /**
   * Delete an MCP server
   */
  deleteServer: (serverId: string) =>
    apiClient.delete(`/mcp/servers/${serverId}/`),

  /**
   * Test connection to an MCP server
   */
  testConnection: (serverId: string) =>
    apiClient.post<{ status: string; message?: string }>(`/mcp/servers/${serverId}/test_connection/`),

  /**
   * Perform health check and update connection status
   */
  healthCheck: (serverId: string) =>
    apiClient.post<{ status: string; is_healthy: boolean; server: MCPServer }>(`/mcp/servers/${serverId}/health_check/`),

  /**
   * Discover tools from an MCP server
   */
  discoverTools: (serverId: string, forceRefresh = false) =>
    apiClient.post<{ tools_count: number; tools: MCPTool[] }>(
      `/mcp/servers/${serverId}/discover_tools/`,
      { force_refresh: forceRefresh }
    ),

  /**
   * Start an MCP server in a sandboxed container
   * Only works for npm-based servers (with npm_package set)
   */
  startSandbox: (serverId: string) =>
    apiClient.post<MCPSandboxStartResponse>(`/mcp/servers/${serverId}/start_sandbox/`),

  /**
   * Stop an MCP server sandbox container
   */
  stopSandbox: (serverId: string, containerId: string) =>
    apiClient.post<{ status: string; message: string }>(
      `/mcp/servers/${serverId}/stop_sandbox/`,
      { container_id: containerId }
    ),

  // ========== Dynamic OAuth ==========

  /**
   * Discover OAuth configuration for a remote MCP server
   * Fetches from /.well-known/oauth-authorization-server
   */
  oauthDiscover: (serverId: string) =>
    apiClient.post<{
      status: string
      metadata: {
        issuer: string
        authorization_endpoint: string
        token_endpoint: string
        registration_endpoint?: string
        scopes_supported: string[]
      }
      supports_dynamic_registration: boolean
      requires_manual_client_id: boolean
    }>(`/mcp/servers/${serverId}/oauth/discover/`),

  /**
   * Start OAuth authorization flow for a server
   * Returns authorization URL to redirect user to
   */
  oauthAuthorize: (serverId: string, credentials?: { client_id?: string; client_secret?: string }) =>
    apiClient.post<{
      status: string
      authorization_url: string
      state: string
    }>(`/mcp/servers/${serverId}/oauth/authorize/`, credentials || {}),

  /**
   * Disconnect OAuth and clear tokens for a server
   */
  oauthDisconnect: (serverId: string) =>
    apiClient.post<{ status: string; message: string }>(`/mcp/servers/${serverId}/oauth/disconnect/`),

  /**
   * Manually refresh OAuth token for a server
   */
  oauthRefresh: (serverId: string) =>
    apiClient.post<{
      status: string
      message: string
      expires_at?: string
    }>(`/mcp/servers/${serverId}/oauth/refresh/`),

  // ========== Configuration Help ==========

  /**
   * Get configuration help for an MCP server
   * Uses LLM to extract required env vars, auth info, setup steps from README
   */
  getConfigHelp: (data: { npm_package?: string; remote_url?: string; server_name?: string; github_url?: string }) =>
    apiClient.post<MCPConfigHelpResponse>('/mcp/servers/config-help/', data),

  /**
   * AI-powered MCP server discovery
   * Searches web and uses LLM to find MCP servers matching user's description
   */
  aiDiscover: (query: string) =>
    apiClient.post<MCPAIDiscoverResponse>('/mcp/servers/ai-discover/', { query }, { timeout: 60000 }),

  /**
   * Get user's AI discovery search history
   */
  getDiscoveryHistory: () =>
    apiClient.get<MCPDiscoveryHistoryEntry[]>('/mcp/servers/discovery-history/'),

  // ========== Tools ==========

  /**
   * List all available MCP tools from all active servers
   */
  listTools: (params?: { server?: string }) =>
    apiClient.get<MCPToolsResponse>('/mcp/tools/', { params }),

  /**
   * Get a specific MCP tool by ID
   */
  getTool: (toolId: string) =>
    apiClient.get<MCPTool>(`/mcp/tools/${toolId}/`),

  /**
   * Request execution of an MCP tool (creates approval request)
   */
  callTool: (toolId: string, arguments_: Record<string, unknown>) =>
    apiClient.post<MCPToolApproval>(`/mcp/tools/${toolId}/call/`, {
      arguments: arguments_
    }),

  // ========== Approvals ==========

  /**
   * List all tool approvals
   */
  listApprovals: (params?: { status?: string; session_id?: string }) =>
    apiClient.get<MCPApprovalsResponse>('/mcp/approvals/', { params }),

  /**
   * Get pending approvals
   */
  getPendingApprovals: (sessionId?: string) =>
    apiClient.get<MCPApprovalsResponse>('/mcp/approvals/pending/', {
      params: sessionId ? { session_id: sessionId } : undefined
    }),

  /**
   * Get a specific approval by ID
   */
  getApproval: (approvalId: string) =>
    apiClient.get<MCPToolApproval>(`/mcp/approvals/${approvalId}/`),

  /**
   * Approve a tool execution
   * Note: MCP tools can take a long time to execute, so we use a longer timeout
   */
  approve: (approvalId: string, scope?: 'once' | 'session' | 'permanent') =>
    apiClient.post<MCPToolApproval>(
      `/mcp/approvals/${approvalId}/approve/`,
      {
        scope: scope || 'once'
      },
      {
        timeout: 120000  // 2 minutes timeout for MCP tool execution
      }
    ),

  /**
   * Reject a tool execution
   */
  reject: (approvalId: string) =>
    apiClient.post<MCPToolApproval>(`/mcp/approvals/${approvalId}/reject/`),

  // ========== Executions ==========

  /**
   * List tool executions
   */
  listExecutions: (params?: { session_id?: string; status?: string }) =>
    apiClient.get<MCPExecutionsResponse>('/mcp/executions/', { params }),

  /**
   * Get recent executions (last 50)
   */
  getRecentExecutions: () =>
    apiClient.get<MCPExecutionsResponse>('/mcp/executions/recent/'),

  /**
   * Get a specific execution by ID
   */
  getExecution: (executionId: string) =>
    apiClient.get<MCPToolExecution>(`/mcp/executions/${executionId}/`),
}
