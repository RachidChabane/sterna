import { create } from 'zustand'
import { subAgentApi, type SubAgent, type SubAgentSummary, type SubAgentCreateData } from '@/api/subAgents'
import { toast } from 'sonner'

const CACHE_TTL_MS = 5 * 60 * 1000 // 5 minutes

interface SubAgentStore {
  // State
  agents: SubAgentSummary[]
  agentsLoading: boolean
  agentsError: string | null
  lastFetchTime: number
  selectedAgent: SubAgent | null
  isGenerating: boolean

  // Actions
  fetchAgents: (forceRefresh?: boolean) => Promise<void>
  getAgent: (id: string) => Promise<SubAgent | null>
  createAgent: (data: SubAgentCreateData) => Promise<SubAgent | null>
  updateAgent: (id: string, data: Partial<SubAgentCreateData>) => Promise<SubAgent | null>
  deleteAgent: (id: string) => Promise<boolean>
  toggleAgent: (id: string) => Promise<void>
  setSelectedAgent: (agent: SubAgent | null) => void
  generateAgent: (description: string) => Promise<SubAgentCreateData | null>
}

export const useSubAgentStore = create<SubAgentStore>()((set, get) => ({
  agents: [],
  agentsLoading: false,
  agentsError: null,
  lastFetchTime: 0,
  selectedAgent: null,
  isGenerating: false,

  fetchAgents: async (forceRefresh = false) => {
    const state = get()
    const now = Date.now()
    if (!forceRefresh && state.lastFetchTime > 0 && now - state.lastFetchTime < CACHE_TTL_MS) {
      return
    }

    set({ agentsLoading: true, agentsError: null })
    try {
      const response = await subAgentApi.list()
      set({
        agents: Array.isArray(response.data) ? response.data : response.data.results ?? [],
        agentsLoading: false,
        lastFetchTime: Date.now(),
      })
    } catch (error: unknown) {
      const msg = error instanceof Error ? error.message : 'Failed to fetch agents'
      set({ agentsLoading: false, agentsError: msg })
    }
  },

  getAgent: async (id: string) => {
    try {
      const response = await subAgentApi.get(id)
      set({ selectedAgent: response.data })
      return response.data
    } catch {
      return null
    }
  },

  createAgent: async (data: SubAgentCreateData) => {
    try {
      const response = await subAgentApi.create(data)
      const newAgent = response.data
      set(state => ({
        agents: [
          {
            id: newAgent.id,
            name: newAgent.name,
            description: newAgent.description,
            model_tier: newAgent.model_tier,
            is_active: newAgent.is_active,
            updated_at: newAgent.updated_at,
          },
          ...state.agents,
        ],
      }))
      return newAgent
    } catch (error: unknown) {
      const msg = error instanceof Error ? error.message : 'Failed to create agent'
      toast.error(msg)
      return null
    }
  },

  updateAgent: async (id: string, data: Partial<SubAgentCreateData>) => {
    try {
      const response = await subAgentApi.update(id, data)
      const updated = response.data
      set(state => ({
        agents: state.agents.map(a =>
          a.id === id
            ? {
                id: updated.id,
                name: updated.name,
                description: updated.description,
                model_tier: updated.model_tier,
                is_active: updated.is_active,
                updated_at: updated.updated_at,
              }
            : a
        ),
        selectedAgent: state.selectedAgent?.id === id ? updated : state.selectedAgent,
      }))
      return updated
    } catch (error: unknown) {
      const msg = error instanceof Error ? error.message : 'Failed to update agent'
      toast.error(msg)
      return null
    }
  },

  deleteAgent: async (id: string) => {
    try {
      await subAgentApi.delete(id)
      set(state => ({
        agents: state.agents.filter(a => a.id !== id),
        selectedAgent: state.selectedAgent?.id === id ? null : state.selectedAgent,
      }))
      return true
    } catch {
      toast.error('Failed to delete agent')
      return false
    }
  },

  toggleAgent: async (id: string) => {
    // Optimistic update
    const prevAgents = get().agents
    set(state => ({
      agents: state.agents.map(a =>
        a.id === id ? { ...a, is_active: !a.is_active } : a
      ),
    }))

    try {
      await subAgentApi.toggleActive(id)
    } catch {
      // Revert on error
      set({ agents: prevAgents })
      toast.error('Failed to toggle agent')
    }
  },

  setSelectedAgent: (agent) => set({ selectedAgent: agent }),

  generateAgent: async (description: string) => {
    set({ isGenerating: true })
    try {
      const response = await subAgentApi.generate(description)
      return response.data
    } catch (error: unknown) {
      const msg = error instanceof Error ? error.message : 'Failed to generate agent'
      toast.error(msg)
      return null
    } finally {
      set({ isGenerating: false })
    }
  },
}))
