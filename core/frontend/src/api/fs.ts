/**
 * File System API
 *
 * API calls for sandbox file system operations
 */

import axios from 'axios'
import { getAccessToken, orchestratorClient } from './client'

interface FSRequest {
  user_id: string
  conversation_id: string
  chat_id?: string
  project_id?: string
  sync_mode?: boolean
}

interface FileNode {
  name: string
  path: string
  type: 'file' | 'directory'
}

export interface FileMetadata {
  path: string
  name: string
  created_by?: {
    model_name: string
    model_id: string
    provider: string
    model_icon_slug?: string
    model_icon_url?: string
    provider_icon_slug?: string
    provider_icon_url?: string
    message_id?: string
    timestamp?: string
  }
  modified_by?: {
    model_name: string
    model_id: string
    provider: string
    model_icon_slug?: string
    model_icon_url?: string
    provider_icon_slug?: string
    provider_icon_url?: string
    message_id?: string
    timestamp?: string
  }
  created_at?: string
  modified_at?: string
  size?: number
}

function requireToken(): void {
  if (!getAccessToken()) throw new Error('No authentication token')
}

/**
 * Unwrap an orchestratorClient response, normalizing an HTTP-level failure
 * to the same `HTTP <status>` message the raw `fetch()` calls this client
 * replaces used to throw on a non-2xx response.
 */
async function unwrap<T>(promise: Promise<{ data: T }>): Promise<T> {
  try {
    const response = await promise
    return response.data
  } catch (err) {
    if (axios.isAxiosError(err) && err.response) {
      throw new Error(`HTTP ${err.response.status}`)
    }
    throw err
  }
}

export const fsAPI = {
  /**
   * List files in directory
   */
  async listFiles(params: FSRequest & { path?: string }): Promise<{ success: boolean; files?: FileNode[]; error?: string }> {
    requireToken()

    return unwrap(orchestratorClient.post('/fs/list', {
      user_id: params.user_id,
      conversation_id: params.conversation_id,
      chat_id: params.chat_id,
      project_id: params.project_id || params.chat_id,
      sync_mode: params.sync_mode ?? true,
      path: params.path || '/workspace',
    }))
  },

  /**
   * Read file content
   */
  async readFile(params: FSRequest & { path: string }): Promise<{ success: boolean; content?: string; error?: string }> {
    requireToken()

    return unwrap(orchestratorClient.post('/fs/read', {
      user_id: params.user_id,
      conversation_id: params.conversation_id,
      chat_id: params.chat_id,
      project_id: params.project_id || params.chat_id,
      sync_mode: params.sync_mode ?? true,
      path: params.path,
    }))
  },

  /**
   * Write file content
   */
  async writeFile(params: FSRequest & { path: string; content: string; is_base64?: boolean }): Promise<{
    success: boolean
    path?: string
    renamed?: boolean
    original_path?: string
    message?: string
    error?: string
  }> {
    requireToken()

    return unwrap(orchestratorClient.post('/fs/write', {
      user_id: params.user_id,
      conversation_id: params.conversation_id,
      chat_id: params.chat_id,
      project_id: params.project_id || params.chat_id,
      sync_mode: params.sync_mode ?? true,
      path: params.path,
      content: params.content,
      is_base64: params.is_base64 ?? false,
    }))
  },

  /**
   * Delete file or directory
   */
  async deleteFile(params: FSRequest & { path: string }): Promise<{ success: boolean; error?: string }> {
    requireToken()

    return unwrap(orchestratorClient.post('/fs/delete', {
      user_id: params.user_id,
      conversation_id: params.conversation_id,
      chat_id: params.chat_id,
      project_id: params.project_id || params.chat_id,
      sync_mode: params.sync_mode ?? true,
      path: params.path,
    }))
  },

  /**
   * Delete entire workspace for a chat or conversation
   */
  async deleteWorkspace(params: FSRequest & { scope?: 'chat' | 'conversation' }): Promise<{
    success: boolean
    message?: string
    deleted_count?: number
    error?: string
  }> {
    requireToken()

    return unwrap(orchestratorClient.post('/fs/delete-workspace', {
      user_id: params.user_id,
      conversation_id: params.conversation_id,
      chat_id: params.chat_id,
      project_id: params.project_id || params.chat_id,
      sync_mode: params.sync_mode ?? true,
      scope: params.scope || 'chat',
    }))
  },

  /**
   * Rename file or directory
   */
  async renameFile(params: FSRequest & { old_path: string; new_path: string }): Promise<{ success: boolean; error?: string }> {
    requireToken()

    return unwrap(orchestratorClient.post('/fs/rename', {
      user_id: params.user_id,
      conversation_id: params.conversation_id,
      chat_id: params.chat_id,
      project_id: params.project_id || params.chat_id,
      sync_mode: params.sync_mode ?? true,
      old_path: params.old_path,
      new_path: params.new_path,
    }))
  },

  /**
   * Create directory
   */
  async createDirectory(params: FSRequest & { path: string }): Promise<{ success: boolean; error?: string }> {
    requireToken()

    return unwrap(orchestratorClient.post('/fs/mkdir', {
      user_id: params.user_id,
      conversation_id: params.conversation_id,
      chat_id: params.chat_id,
      project_id: params.project_id || params.chat_id,
      sync_mode: params.sync_mode ?? true,
      path: params.path,
    }))
  },

  /**
   * Get file metadata (creator, last modifier, timestamps)
   */
  async getFileMetadata(params: FSRequest & { path: string }): Promise<{ success: boolean; metadata?: FileMetadata; error?: string }> {
    requireToken()

    return unwrap(orchestratorClient.post('/fs/metadata', {
      user_id: params.user_id,
      conversation_id: params.conversation_id,
      chat_id: params.chat_id,
      project_id: params.project_id || params.chat_id,
      sync_mode: params.sync_mode ?? true,
      path: params.path,
    }))
  },

  /**
   * Save workspace files to persistent storage (PostgreSQL + R2)
   * Should be called when closing IDE to persist files
   */
  async saveWorkspace(params: { user_id: string; chat_id: string }): Promise<{
    success: boolean
    files_synced: number
    bytes_synced: number
    files_deleted: number
    errors: string[]
    duration_ms?: number
  }> {
    requireToken()

    return unwrap(orchestratorClient.post('/workspace/save', {
      user_id: params.user_id,
      chat_id: params.chat_id,
    }))
  },

  /**
   * Restore workspace files from persistent storage (PostgreSQL + R2)
   * Should be called when opening IDE to restore previously saved files
   */
  async restoreWorkspace(params: { user_id: string; chat_id: string }): Promise<{
    success: boolean
    files_synced: number
    bytes_synced: number
    errors: string[]
    duration_ms?: number
    was_restored?: boolean  // True if files were actually restored from storage
  }> {
    requireToken()

    return unwrap(orchestratorClient.post('/workspace/restore', {
      user_id: params.user_id,
      chat_id: params.chat_id,
    }))
  },

  /**
   * Get workspace info from persistent storage
   */
  async getWorkspaceInfo(params: { user_id: string; chat_id: string }): Promise<{
    exists: boolean
    file_count?: number
    total_size?: number
    last_synced?: string
  }> {
    requireToken()

    return unwrap(orchestratorClient.get(`/workspace/info/${params.user_id}/${params.chat_id}`))
  },

  /**
   * Get workspace resource stats (storage + memory usage)
   */
  async getWorkspaceStats(params: { user_id: string; chat_id: string }): Promise<{
    success: boolean
    storage_used_mb: number
    storage_total_mb: number
    storage_percent: number
    memory_used_mb: number
    memory_total_mb: number
    memory_percent: number
    error?: string
  }> {
    requireToken()

    return unwrap(orchestratorClient.post('/workspace/stats', {
      user_id: params.user_id,
      chat_id: params.chat_id,
    }))
  },
}
