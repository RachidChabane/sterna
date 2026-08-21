/**
 * Zustand store for MCP (Model Context Protocol) state management
 */

import { create } from 'zustand'
import { mcpApi } from '../api/mcp'
import type {
  MCPServer,
  MCPTool,
  MCPToolApproval,
  MCPToolExecution,
  MCPPreconfiguredServer,
} from '../api/mcp'

// Cache TTL: 5 minutes
const CACHE_TTL = 5 * 60 * 1000

interface MCPStore {
  // ========== State ==========

  // Servers
  servers: MCPServer[]
  serversLoading: boolean
  serversError: string | null
  lastServersFetchTime: number

  // Preconfigured servers (browse catalog)
  preconfiguredServers: MCPPreconfiguredServer[]
  preconfiguredServersLoading: boolean
  preconfiguredServersError: string | null
  lastPreconfiguredFetchTime: number

  // Tools
  tools: MCPTool[]
  toolsLoading: boolean
  toolsError: string | null

  // Pending approvals
  pendingApprovals: MCPToolApproval[]
  approvalsLoading: boolean
  approvalsError: string | null

  // Recent executions
  recentExecutions: MCPToolExecution[]
  executionsLoading: boolean
  executionsError: string | null

  // ========== Actions ==========

  // Server actions
  fetchServers: (forceRefresh?: boolean) => Promise<void>
  fetchPreconfiguredServers: (forceRefresh?: boolean) => Promise<void>
  fetchAllMCPData: (forceRefresh?: boolean) => Promise<void>
  createServer: (data: Parameters<typeof mcpApi.createServer>[0]) => Promise<MCPServer | null>
  updateServer: (serverId: string, data: Parameters<typeof mcpApi.updateServer>[1]) => Promise<MCPServer | null>
  deleteServer: (serverId: string) => Promise<boolean>
  testConnection: (serverId: string) => Promise<{ status: string; message?: string } | null>
  healthCheckServer: (serverId: string) => Promise<boolean>
  discoverTools: (serverId: string, forceRefresh?: boolean) => Promise<void>

  // Tool actions
  fetchTools: () => Promise<void>
  callTool: (toolId: string, arguments_: Record<string, unknown>) => Promise<MCPToolApproval | null>

  // Approval actions
  fetchPendingApprovals: (sessionId?: string) => Promise<void>
  approveTool: (approvalId: string, scope?: 'once' | 'session' | 'permanent') => Promise<MCPToolApproval | null>
  rejectTool: (approvalId: string) => Promise<MCPToolApproval | null>

  // Execution actions
  fetchRecentExecutions: () => Promise<void>

  // Computed getters
  getActiveServers: () => MCPServer[]
  getToolsForServer: (serverId: string) => MCPTool[]
  getTotalToolsCount: () => number
}

export const useMCPStore = create<MCPStore>()((set, get) => ({
  // ========== Initial State ==========

  servers: [],
  serversLoading: false,
  serversError: null,
  lastServersFetchTime: 0,

  preconfiguredServers: [],
  preconfiguredServersLoading: false,
  preconfiguredServersError: null,
  lastPreconfiguredFetchTime: 0,

  tools: [],
  toolsLoading: false,
  toolsError: null,

  pendingApprovals: [],
  approvalsLoading: false,
  approvalsError: null,

  recentExecutions: [],
  executionsLoading: false,
  executionsError: null,

  // ========== Server Actions ==========

  fetchServers: async (forceRefresh = false) => {
    const state = get()
    const isCacheValid = Date.now() - state.lastServersFetchTime < CACHE_TTL

    // Skip fetch if cache is valid and not forcing refresh
    if (!forceRefresh && state.servers.length > 0 && isCacheValid && !state.serversLoading) {
      return
    }

    set({ serversLoading: true, serversError: null })
    try {
      const response = await mcpApi.listServers()
      set({
        servers: response.data.results,
        serversLoading: false,
        lastServersFetchTime: Date.now(),
      })
    } catch (error: any) {
      console.error('Failed to fetch MCP servers:', error)
      set({
        serversError: error.message || 'Failed to fetch servers',
        serversLoading: false
      })
    }
  },

  fetchPreconfiguredServers: async (forceRefresh = false) => {
    const state = get()
    const isCacheValid = Date.now() - state.lastPreconfiguredFetchTime < CACHE_TTL

    // Skip fetch if cache is valid and not forcing refresh
    if (!forceRefresh && state.preconfiguredServers.length > 0 && isCacheValid && !state.preconfiguredServersLoading) {
      return
    }

    set({ preconfiguredServersLoading: true, preconfiguredServersError: null })
    try {
      const response = await mcpApi.listPreconfiguredServers({ page: 1, page_size: 200 })
      set({
        preconfiguredServers: response.data.results,
        preconfiguredServersLoading: false,
        lastPreconfiguredFetchTime: Date.now(),
      })
    } catch (error: any) {
      console.error('Failed to fetch preconfigured MCP servers:', error)
      set({
        preconfiguredServersError: error.message || 'Failed to fetch preconfigured servers',
        preconfiguredServersLoading: false
      })
    }
  },

  // Fetch both servers and preconfigured servers in parallel
  fetchAllMCPData: async (forceRefresh = false) => {
    const { fetchServers, fetchPreconfiguredServers } = get()
    await Promise.all([
      fetchServers(forceRefresh),
      fetchPreconfiguredServers(forceRefresh),
    ])
  },

  createServer: async (data) => {
    set({ serversError: null })
    try {
      const response = await mcpApi.createServer(data)
      const newServer = response.data

      // Add to servers list
      set(state => ({
        servers: [...state.servers, newServer]
      }))

      return newServer
    } catch (error: any) {
      console.error('Failed to create MCP server:', error)
      set({ serversError: error.message || 'Failed to create server' })
      return null
    }
  },

  updateServer: async (serverId, data) => {
    set({ serversError: null })
    try {
      const response = await mcpApi.updateServer(serverId, data)
      const updatedServer = response.data

      // Update in servers list
      set(state => ({
        servers: state.servers.map(s => s.id === serverId ? updatedServer : s)
      }))

      return updatedServer
    } catch (error: any) {
      console.error('Failed to update MCP server:', error)
      set({ serversError: error.message || 'Failed to update server' })
      return null
    }
  },

  deleteServer: async (serverId) => {
    set({ serversError: null })
    try {
      await mcpApi.deleteServer(serverId)

      // Remove from servers list
      set(state => ({
        servers: state.servers.filter(s => s.id !== serverId),
        // Also remove associated tools
        tools: state.tools.filter(t => t.server.id !== serverId)
      }))

      return true
    } catch (error: any) {
      console.error('Failed to delete MCP server:', error)
      set({ serversError: error.message || 'Failed to delete server' })
      return false
    }
  },

  testConnection: async (serverId) => {
    try {
      const response = await mcpApi.testConnection(serverId)
      return response.data
    } catch (error: any) {
      console.error('Failed to test MCP server connection:', error)
      return null
    }
  },

  healthCheckServer: async (serverId) => {
    try {
      const response = await mcpApi.healthCheck(serverId)
      const updatedServer = response.data.server

      // Update server in the list with fresh connection status
      set(state => ({
        servers: state.servers.map(s => s.id === serverId ? updatedServer : s)
      }))

      return response.data.is_healthy
    } catch (error: any) {
      console.error('Failed to perform health check:', error)
      return false
    }
  },

  discoverTools: async (serverId, forceRefresh = false) => {
    set({ toolsError: null })
    try {
      const response = await mcpApi.discoverTools(serverId, forceRefresh)

      // Update tools list with discovered tools
      const newTools = response.data.tools
      set(state => ({
        // Remove old tools from this server, add new ones
        tools: [
          ...state.tools.filter(t => t.server.id !== serverId),
          ...newTools
        ]
      }))
    } catch (error: any) {
      console.error('Failed to discover MCP tools:', error)
      set({ toolsError: error.message || 'Failed to discover tools' })
    }
  },

  // ========== Tool Actions ==========

  fetchTools: async () => {
    set({ toolsLoading: true, toolsError: null })
    try {
      const response = await mcpApi.listTools()
      set({
        tools: response.data.results,
        toolsLoading: false
      })
    } catch (error: any) {
      console.error('Failed to fetch MCP tools:', error)
      set({
        toolsError: error.message || 'Failed to fetch tools',
        toolsLoading: false
      })
    }
  },

  callTool: async (toolId, arguments_) => {
    try {
      const response = await mcpApi.callTool(toolId, arguments_)
      const approval = response.data

      // Add to pending approvals if it's pending
      if (approval.status === 'pending') {
        set(state => ({
          pendingApprovals: [...state.pendingApprovals, approval]
        }))
      }

      return approval
    } catch (error: any) {
      console.error('Failed to call MCP tool:', error)
      return null
    }
  },

  // ========== Approval Actions ==========

  fetchPendingApprovals: async (sessionId?: string) => {
    set({ approvalsLoading: true, approvalsError: null })
    try {
      const response = await mcpApi.getPendingApprovals(sessionId)
      set({
        pendingApprovals: response.data.results,
        approvalsLoading: false
      })
    } catch (error: any) {
      console.error('Failed to fetch pending approvals:', error)
      set({
        approvalsError: error.message || 'Failed to fetch approvals',
        approvalsLoading: false
      })
    }
  },

  approveTool: async (approvalId, scope = 'once') => {
    try {
      const response = await mcpApi.approve(approvalId, scope)
      const approvedApproval = response.data

      // Remove from pending approvals
      set(state => ({
        pendingApprovals: state.pendingApprovals.filter(a => a.id !== approvalId)
      }))

      return approvedApproval
    } catch (error: any) {
      console.error('Failed to approve tool:', error)
      return null
    }
  },

  rejectTool: async (approvalId) => {
    try {
      const response = await mcpApi.reject(approvalId)
      const rejectedApproval = response.data

      // Remove from pending approvals
      set(state => ({
        pendingApprovals: state.pendingApprovals.filter(a => a.id !== approvalId)
      }))

      return rejectedApproval
    } catch (error: any) {
      console.error('Failed to reject tool:', error)
      return null
    }
  },

  // ========== Execution Actions ==========

  fetchRecentExecutions: async () => {
    set({ executionsLoading: true, executionsError: null })
    try {
      const response = await mcpApi.getRecentExecutions()
      set({
        recentExecutions: response.data.results,
        executionsLoading: false
      })
    } catch (error: any) {
      console.error('Failed to fetch recent executions:', error)
      set({
        executionsError: error.message || 'Failed to fetch executions',
        executionsLoading: false
      })
    }
  },

  // ========== Computed Getters ==========

  getActiveServers: () => {
    return get().servers.filter(s => s.is_active)
  },

  getToolsForServer: (serverId: string) => {
    return get().tools.filter(t => t.server.id === serverId)
  },

  getTotalToolsCount: () => {
    return get().tools.length
  },
}))
