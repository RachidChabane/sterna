/**
 * File Versioning API Client
 *
 * Endpoints for file version history, content retrieval, and comparison.
 */

import apiClient from './client'

// Types

interface FileVersion {
  id: string
  version_number: number
  path: string
  source_type: 'user_edit' | 'file_tool' | 'coding_agent' | 'upload' | 'restore' | 'initial'
  source_type_display: string
  source_message_id?: string | null
  source_job_id?: string | null
  source_tool_name?: string | null
  size_bytes: number
  is_deleted: boolean
  is_binary: boolean
  mime_type: string
  created_at: string
  created_by?: {
    id: string
    username: string
  } | null
}

export interface FileHistoryResponse {
  path: string
  total_versions: number
  versions: FileVersion[]
}

export interface VersionContentResponse {
  version_id: string
  path: string
  version_number: number
  is_binary: boolean
  size_bytes: number
  mime_type: string
  content: string | null
}

interface VersionInfo {
  id: string
  version_number: number
  source_type: string
  source_type_display: string
  created_at: string
}

export interface CompareVersionsResponse {
  path: string
  version_a: VersionInfo
  version_b: VersionInfo
  is_binary: boolean
  original_content: string | null
  modified_content: string | null
}

interface TimelineEntry {
  id: string
  path: string
  filename: string
  version_number: number
  source_type: string
  source_type_display: string
  source_job_id?: string | null
  source_tool_name?: string | null
  size_bytes: number
  is_deleted: boolean
  is_binary: boolean
  created_at: string
}

export interface WorkspaceTimelineResponse {
  chat_id: string
  total_entries: number
  timeline: TimelineEntry[]
}

interface FileChangeVersion {
  id: string
  version_number: number
  is_deleted: boolean
  size_bytes: number
  created_at: string
}

export interface MessageFileChange {
  path: string
  filename: string
  change_type: 'created' | 'modified' | 'deleted'
  is_binary: boolean
  versions: FileChangeVersion[]
}

export interface MessageFileChangesResponse {
  message_id: string
  files: MessageFileChange[]
}

export interface JobFileChangesResponse {
  job_id: string
  files: MessageFileChange[]
}

// API Client

export const versionsApi = {
  /**
   * Get version history for a specific file.
   */
  getFileHistory: (chatId: string, path: string, limit = 50) =>
    apiClient.get<FileHistoryResponse>(`/workspaces/${chatId}/files/history/`, {
      params: { path, limit }
    }),

  /**
   * Get content of a specific version.
   */
  getVersionContent: (versionId: string) =>
    apiClient.get<VersionContentResponse>(`/workspaces/versions/${versionId}/content/`),

  /**
   * Compare two versions of a file.
   * @param versionAId - Older version (original)
   * @param versionBId - Newer version (modified)
   */
  compareVersions: (versionAId: string, versionBId: string) =>
    apiClient.get<CompareVersionsResponse>('/workspaces/versions/compare/', {
      params: { a: versionAId, b: versionBId }
    }),

  /**
   * Get timeline of all changes in a workspace.
   */
  getWorkspaceTimeline: (chatId: string, sourceType?: string, limit = 100) =>
    apiClient.get<WorkspaceTimelineResponse>(`/workspaces/${chatId}/timeline/`, {
      params: { source_type: sourceType, limit }
    }),

  /**
   * Get all file changes from a specific message.
   */
  getMessageFileChanges: (messageId: string) =>
    apiClient.get<MessageFileChangesResponse>(`/workspaces/messages/${messageId}/file-changes/`),

  /**
   * Get all file changes from a Coding Agent job.
   */
  getJobFileChanges: (jobId: string) =>
    apiClient.get<JobFileChangesResponse>(`/workspaces/jobs/${jobId}/file-changes/`),
}

// Helper functions

