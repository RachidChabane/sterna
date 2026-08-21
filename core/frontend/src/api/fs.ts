/**
 * File System API
 *
 * API calls for sandbox file system operations
 */

import { getAccessToken, ORCHESTRATOR_URL } from './client'

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

export const fsAPI = {
  /**
   * List files in directory
   */
  async listFiles(params: FSRequest & { path?: string }): Promise<{ success: boolean; files?: FileNode[]; error?: string }> {
    const token = getAccessToken()
    if (!token) throw new Error('No authentication token')

    const response = await fetch(`${ORCHESTRATOR_URL}/fs/list`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`,
      },
      body: JSON.stringify({
        user_id: params.user_id,
        conversation_id: params.conversation_id,
        chat_id: params.chat_id,
        project_id: params.project_id || params.chat_id,
        sync_mode: params.sync_mode ?? true,
        path: params.path || '/workspace',
      }),
    })

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`)
    }

    return response.json()
  },

  /**
   * Read file content
   */
  async readFile(params: FSRequest & { path: string }): Promise<{ success: boolean; content?: string; error?: string }> {
    const token = getAccessToken()
    if (!token) throw new Error('No authentication token')

    const response = await fetch(`${ORCHESTRATOR_URL}/fs/read`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`,
      },
      body: JSON.stringify({
        user_id: params.user_id,
        conversation_id: params.conversation_id,
        chat_id: params.chat_id,
        project_id: params.project_id || params.chat_id,
        sync_mode: params.sync_mode ?? true,
        path: params.path,
      }),
    })

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`)
    }

    return response.json()
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
    const token = getAccessToken()
    if (!token) throw new Error('No authentication token')

    const response = await fetch(`${ORCHESTRATOR_URL}/fs/write`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`,
      },
      body: JSON.stringify({
        user_id: params.user_id,
        conversation_id: params.conversation_id,
        chat_id: params.chat_id,
        project_id: params.project_id || params.chat_id,
        sync_mode: params.sync_mode ?? true,
        path: params.path,
        content: params.content,
        is_base64: params.is_base64 ?? false,
      }),
    })

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`)
    }

    return response.json()
  },

  /**
   * Delete file or directory
   */
  async deleteFile(params: FSRequest & { path: string }): Promise<{ success: boolean; error?: string }> {
    const token = getAccessToken()
    if (!token) throw new Error('No authentication token')

    const response = await fetch(`${ORCHESTRATOR_URL}/fs/delete`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`,
      },
      body: JSON.stringify({
        user_id: params.user_id,
        conversation_id: params.conversation_id,
        chat_id: params.chat_id,
        project_id: params.project_id || params.chat_id,
        sync_mode: params.sync_mode ?? true,
        path: params.path,
      }),
    })

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`)
    }

    return response.json()
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
    const token = getAccessToken()
    if (!token) throw new Error('No authentication token')

    const response = await fetch(`${ORCHESTRATOR_URL}/fs/delete-workspace`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`,
      },
      body: JSON.stringify({
        user_id: params.user_id,
        conversation_id: params.conversation_id,
        chat_id: params.chat_id,
        project_id: params.project_id || params.chat_id,
        sync_mode: params.sync_mode ?? true,
        scope: params.scope || 'chat',
      }),
    })

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`)
    }

    return response.json()
  },

  /**
   * Rename file or directory
   */
  async renameFile(params: FSRequest & { old_path: string; new_path: string }): Promise<{ success: boolean; error?: string }> {
    const token = getAccessToken()
    if (!token) throw new Error('No authentication token')

    const response = await fetch(`${ORCHESTRATOR_URL}/fs/rename`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`,
      },
      body: JSON.stringify({
        user_id: params.user_id,
        conversation_id: params.conversation_id,
        chat_id: params.chat_id,
        project_id: params.project_id || params.chat_id,
        sync_mode: params.sync_mode ?? true,
        old_path: params.old_path,
        new_path: params.new_path,
      }),
    })

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`)
    }

    return response.json()
  },

  /**
   * Create directory
   */
  async createDirectory(params: FSRequest & { path: string }): Promise<{ success: boolean; error?: string }> {
    const token = getAccessToken()
    if (!token) throw new Error('No authentication token')

    const response = await fetch(`${ORCHESTRATOR_URL}/fs/mkdir`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`,
      },
      body: JSON.stringify({
        user_id: params.user_id,
        conversation_id: params.conversation_id,
        chat_id: params.chat_id,
        project_id: params.project_id || params.chat_id,
        sync_mode: params.sync_mode ?? true,
        path: params.path,
      }),
    })

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`)
    }

    return response.json()
  },

  /**
   * Get file metadata (creator, last modifier, timestamps)
   */
  async getFileMetadata(params: FSRequest & { path: string }): Promise<{ success: boolean; metadata?: FileMetadata; error?: string }> {
    const token = getAccessToken()
    if (!token) throw new Error('No authentication token')

    const response = await fetch(`${ORCHESTRATOR_URL}/fs/metadata`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`,
      },
      body: JSON.stringify({
        user_id: params.user_id,
        conversation_id: params.conversation_id,
        chat_id: params.chat_id,
        project_id: params.project_id || params.chat_id,
        sync_mode: params.sync_mode ?? true,
        path: params.path,
      }),
    })

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`)
    }

    return response.json()
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
    const token = getAccessToken()
    if (!token) throw new Error('No authentication token')

    const response = await fetch(`${ORCHESTRATOR_URL}/workspace/save`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`,
      },
      body: JSON.stringify({
        user_id: params.user_id,
        chat_id: params.chat_id,
      }),
    })

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`)
    }

    return response.json()
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
    const token = getAccessToken()
    if (!token) throw new Error('No authentication token')

    const response = await fetch(`${ORCHESTRATOR_URL}/workspace/restore`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`,
      },
      body: JSON.stringify({
        user_id: params.user_id,
        chat_id: params.chat_id,
      }),
    })

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`)
    }

    return response.json()
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
    const token = getAccessToken()
    if (!token) throw new Error('No authentication token')

    const response = await fetch(`${ORCHESTRATOR_URL}/workspace/info/${params.user_id}/${params.chat_id}`, {
      method: 'GET',
      headers: {
        'Authorization': `Bearer ${token}`,
      },
    })

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`)
    }

    return response.json()
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
    const token = getAccessToken()
    if (!token) throw new Error('No authentication token')

    const response = await fetch(`${ORCHESTRATOR_URL}/workspace/stats`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`,
      },
      body: JSON.stringify({
        user_id: params.user_id,
        chat_id: params.chat_id,
      }),
    })

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`)
    }

    return response.json()
  },
}
