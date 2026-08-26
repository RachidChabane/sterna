/**
 * Sparks API Client
 *
 * Handles creation, retrieval, and management of Sparks (interactive components).
 * Sparks are stored with versioning support and tiered storage (inline/R2).
 */

import { api } from './client'
import type { components } from './generated/schema'

// ============================================================================
// Types
// ============================================================================

/**
 * Framework types supported by Sparks
 */
export type SparkFramework = components['schemas']['FrameworkEnum']

/**
 * Asset referenced by a spark (image/video)
 */
export interface SparkAsset {
  id: string
  url: string
  type: 'image' | 'video'
  filename: string
  width?: number | null
  height?: number | null
}

/**
 * Spark metadata returned from the API
 */
export interface Spark {
  id: string
  title: string
  framework: SparkFramework
  code: string
  dependencies: string[]
  assets?: SparkAsset[]  // Assets available via window.__SPARK_ASSETS__
  download_url?: string | null  // For csv/ics/pdf/docx types
  latest_deployment?: SparkLatestDeployment | null
  is_ignited?: boolean
  version: number
  parent_id: string | null
  chat_id: string | null
  chat_name: string | null
  conversation_id: string | null
  message_id: string | null
  created_at: string
  updated_at: string
}

/**
 * Spark definition extracted from LLM response
 */
export interface SparkDefinition {
  id?: string           // For updates
  title: string
  framework: SparkFramework
  code: string
}

/**
 * Request payload for creating a spark
 */
export type CreateSparkRequest = components['schemas']['SparkCreate']

/**
 * Request payload for updating a spark (creates new version)
 */
export type UpdateSparkRequest = components['schemas']['SparkUpdate']

/**
 * Response from listing sparks
 */
export interface SparkListResponse {
  count: number
  next: string | null
  previous: string | null
  results: Spark[]
}

/**
 * Spark version history entry
 */
export interface SparkVersion {
  id: string
  version: number
  title: string
  created_at: string
}

/**
 * Full spark deployment record
 */
export interface SparkDeployment {
  id: string
  status: 'pending' | 'deploying' | 'deployed' | 'failed'
  preview_url: string
  claim_url: string
  deployment_id: string
  project_id: string
  error_message: string
  cost_usd: number
  created_at: string
  updated_at: string
}

/**
 * Latest deployment summary (embedded in Spark responses)
 */
interface SparkLatestDeployment {
  id: string
  status: string
  preview_url: string
  claim_url: string
}

// ============================================================================
// API Client
// ============================================================================

export const sparksAPI = {
  /**
   * Create a new spark
   */
  async create(request: CreateSparkRequest): Promise<Spark | null> {
    try {
      const response = await api.post('/sparks/', request)
      return response.data
    } catch (error: any) {
      console.error('[sparksAPI] Create failed:', error)
      throw new Error(error.response?.data?.error || error.message || 'Failed to create spark')
    }
  },

  /**
   * Get a spark by ID
   */
  async get(sparkId: string): Promise<Spark | null> {
    try {
      const response = await api.get(`/sparks/${sparkId}/`)
      return response.data
    } catch (error) {
      console.error('[sparksAPI] Get failed:', error)
      return null
    }
  },

  /**
   * Update a spark (creates a new version)
   */
  async update(sparkId: string, request: UpdateSparkRequest): Promise<Spark | null> {
    try {
      const response = await api.put(`/sparks/${sparkId}/`, request)
      return response.data
    } catch (error: any) {
      console.error('[sparksAPI] Update failed:', error)
      throw new Error(error.response?.data?.error || error.message || 'Failed to update spark')
    }
  },

  /**
   * Delete a spark
   */
  async delete(sparkId: string): Promise<boolean> {
    try {
      await api.delete(`/sparks/${sparkId}/`)
      return true
    } catch (error) {
      console.error('[sparksAPI] Delete failed:', error)
      return false
    }
  },

  /**
   * List all sparks for the current user
   */
  async list(params?: {
    page?: number
    page_size?: number
    chat_id?: string
    ordering?: string
    search?: string
    framework?: string
  }): Promise<SparkListResponse> {
    try {
      const response = await api.get('/sparks/', { params })
      return response.data
    } catch (error) {
      console.error('[sparksAPI] List failed:', error)
      return {
        count: 0,
        next: null,
        previous: null,
        results: [],
      }
    }
  },

  /**
   * Get the code content for a spark
   * (Handles R2 storage transparently)
   */
  async getCode(sparkId: string): Promise<string | null> {
    try {
      const response = await api.get(`/sparks/${sparkId}/code/`)
      return response.data.code
    } catch (error) {
      console.error('[sparksAPI] Get code failed:', error)
      return null
    }
  },

  /**
   * Get version history for a spark
   */
  async getVersions(sparkId: string): Promise<SparkVersion[]> {
    try {
      const response = await api.get(`/sparks/${sparkId}/versions/`)
      // Backend returns array directly, not wrapped in { versions: [...] }
      const data = response.data
      // Handle both formats: direct array or wrapped in { versions: [...] }
      const versions = Array.isArray(data) ? data : (data.versions || [])
      // Sort by version number descending (newest first)
      return versions.sort((a: SparkVersion, b: SparkVersion) => b.version - a.version)
    } catch (error) {
      console.error('[sparksAPI] Get versions failed:', error)
      return []
    }
  },

  /**
   * Get deployments for a spark
   */
  async getDeployments(sparkId: string): Promise<SparkDeployment[]> {
    try {
      const response = await api.get(`/sparks/${sparkId}/deployments/`)
      return response.data
    } catch (error) {
      console.error('[sparksAPI] Get deployments failed:', error)
      return []
    }
  },

  /**
   * Deploy a spark's project to Vercel (POST /api/sparks/{id}/deploy/)
   */
  async deploy(sparkId: string): Promise<SparkDeployment> {
    const response = await api.post(`/sparks/${sparkId}/deploy/`)
    return response.data
  },

  /**
   * Create multiple sparks from LLM response
   * Batch creation for efficiency
   */
  async createBatch(
    sparks: SparkDefinition[],
    chatId?: string,
    messageId?: string
  ): Promise<Spark[]> {
    const results: Spark[] = []
    for (const spark of sparks) {
      try {
        const created = await this.create({
          title: spark.title,
          framework: spark.framework,
          code: spark.code,
          chat_id: chatId,
          message_id: messageId,
        })
        if (created) {
          results.push(created)
        }
      } catch (error) {
        console.error('[sparksAPI] Batch create failed for spark:', spark.title, error)
      }
    }
    return results
  },
}
