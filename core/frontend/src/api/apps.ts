/**
 * Apps API Client
 *
 * Handles retrieval and management of Apps (ignited Spark projects).
 */

import { api } from './client'

// ============================================================================
// Types
// ============================================================================

export interface App {
  id: string
  title: string
  version: number
  spark_id: string
  spark_title: string
  spark_framework: string
  chat_id: string | null
  conversation_id: string | null
  project_path: string
  preview_command: string
  latest_deployment?: {
    id: string
    status: string
    preview_url: string
    claim_url: string
  } | null
  created_at: string
  updated_at: string
}

export interface AppListItem {
  id: string
  title: string
  version: number
  spark_id: string
  spark_title: string
  spark_framework: string
  chat_id: string | null
  conversation_id: string | null
  created_at: string
  updated_at: string
}

export interface AppListResponse {
  count: number
  next: string | null
  previous: string | null
  results: AppListItem[]
}

export interface PreviewStatus {
  running: boolean
  port: number | null
}

export interface StartPreviewResult {
  pid: number
  port: number
  command: string
  status: string
}

// ============================================================================
// API Client
// ============================================================================

export const appsAPI = {
  async list(params?: {
    page?: number
    page_size?: number
    chat_id?: string
  }): Promise<AppListResponse> {
    try {
      const response = await api.get('/apps/', { params })
      return response.data
    } catch (error) {
      console.error('[appsAPI] List failed:', error)
      return { count: 0, next: null, previous: null, results: [] }
    }
  },

  async get(appId: string): Promise<App | null> {
    try {
      const response = await api.get(`/apps/${appId}/`)
      return response.data
    } catch (error) {
      console.error('[appsAPI] Get failed:', error)
      return null
    }
  },

  async startPreview(appId: string): Promise<StartPreviewResult> {
    const response = await api.post(`/apps/${appId}/start_preview/`)
    return response.data
  },

  async stopPreview(appId: string, port?: number): Promise<{ success: boolean }> {
    const response = await api.post(
      `/apps/${appId}/stop_preview/`,
      port ? { port } : {},
    )
    return response.data
  },

  async previewStatus(appId: string): Promise<PreviewStatus> {
    try {
      const response = await api.get(`/apps/${appId}/preview_status/`)
      return response.data
    } catch (error) {
      console.error('[appsAPI] Preview status failed:', error)
      return { running: false, port: null }
    }
  },

  async getVersions(appId: string): Promise<AppListItem[]> {
    try {
      const response = await api.get(`/apps/${appId}/versions/`)
      return response.data
    } catch (error) {
      console.error('[appsAPI] Get versions failed:', error)
      return []
    }
  },
}
