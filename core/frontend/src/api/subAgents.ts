import apiClient from './client'

// ==================== Types ====================

export type ModelTier = 'fast' | 'balanced' | 'powerful' | 'inherit'

export interface SubAgent {
  id: string
  name: string
  description: string
  model_tier: ModelTier
  system_prompt: string
  tools: string[]
  disallowed_tools: string[]
  max_turns: number
  permission_mode: 'default' | 'plan' | 'autoEdit' | 'fullAuto'
  is_active: boolean
  created_at: string
  updated_at: string
}

export interface SubAgentSummary {
  id: string
  name: string
  description: string
  model_tier: ModelTier
  is_active: boolean
  updated_at: string
}

export interface SubAgentCreateData {
  name: string
  description?: string
  model_tier?: ModelTier
  system_prompt?: string
  tools?: string[]
  disallowed_tools?: string[]
  max_turns?: number
  permission_mode?: string
  is_active?: boolean
}

export interface SubAgentExportResponse {
  markdown: string
  filename: string
}

export interface UserModelPreferences {
  fast_model_id: string
  balanced_model_id: string
  powerful_model_id: string
  updated_at: string
}

// ==================== API Client ====================

// DRF global PageNumberPagination wraps list responses; keep the bare
// array in the union for endpoints with pagination disabled.
export interface PaginatedSubAgents {
  count: number
  next: string | null
  previous: string | null
  results: SubAgentSummary[]
}

export const subAgentApi = {
  list: (params?: { is_active?: boolean }) =>
    apiClient.get<SubAgentSummary[] | PaginatedSubAgents>('/code-sessions/sub-agents/', { params }),

  get: (id: string) =>
    apiClient.get<SubAgent>(`/code-sessions/sub-agents/${id}/`),

  create: (data: SubAgentCreateData) =>
    apiClient.post<SubAgent>('/code-sessions/sub-agents/', data),

  update: (id: string, data: Partial<SubAgentCreateData>) =>
    apiClient.patch<SubAgent>(`/code-sessions/sub-agents/${id}/`, data),

  delete: (id: string) =>
    apiClient.delete(`/code-sessions/sub-agents/${id}/`),

  toggleActive: (id: string) =>
    apiClient.post<SubAgent>(`/code-sessions/sub-agents/${id}/toggle_active/`),

  exportMd: (id: string) =>
    apiClient.get<SubAgentExportResponse>(`/code-sessions/sub-agents/${id}/export_md/`),

  importMd: (content: string) =>
    apiClient.post<SubAgent>('/code-sessions/sub-agents/import_md/', { content }),

  generate: (description: string) =>
    apiClient.post<SubAgentCreateData>('/code-sessions/sub-agents/generate/', { description }),

  activeList: () =>
    apiClient.get<{ results: Array<{ id: string; name: string; description: string; model_tier: ModelTier }> }>(
      '/code-sessions/sub-agents/active_list/'
    ),
}

export const modelPreferencesApi = {
  get: () =>
    apiClient.get<UserModelPreferences>('/settings/coding-agent-models/'),

  update: (data: Partial<Omit<UserModelPreferences, 'updated_at'>>) =>
    apiClient.patch<UserModelPreferences>('/settings/coding-agent-models/', data),
}
