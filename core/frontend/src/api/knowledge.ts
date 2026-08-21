/**
 * Knowledge Base API client
 *
 * Provides typed API calls for the Knowledge Base feature:
 * - Settings management
 * - Document upload/delete/list
 * - Search/query
 * - Query logs
 */

import apiClient from './client'

// ========== Types ==========

export interface KnowledgeSettings {
  is_enabled: boolean
  similarity_threshold: number
  max_chunks_per_query: number
  storage_limit_mb: number
  total_documents: number
  total_chunks: number
  total_storage_bytes: number
  storage_used_mb: number
  storage_percentage: number
  created_at: string
  updated_at: string
}

export type DocumentType = 'pdf' | 'docx' | 'txt' | 'md' | 'csv' | 'html' | 'json'
export type DocumentStatus = 'pending' | 'processing' | 'indexing' | 'ready' | 'failed'

export interface KnowledgeDocument {
  id: string
  filename: string
  original_filename: string
  document_type: DocumentType
  file_size_bytes: number
  file_size_display: string
  status: DocumentStatus
  error_message?: string
  chunk_count: number
  page_count?: number
  word_count?: number
  tags: string[]
  uploaded_at: string
  processed_at?: string
  last_queried_at?: string
}

export interface KnowledgeDocumentDetail extends KnowledgeDocument {
  chunks_preview?: {
    id: string
    content: string
    chunk_index: number
    page_number?: number
  }[]
}

export interface SearchResult {
  chunk_id: string
  document_id: string
  document_filename: string
  document_type: DocumentType
  content: string
  chunk_index: number
  page_number?: number
  similarity_score: number
  token_count: number
}

export interface SearchResponse {
  results: SearchResult[]
  query_id: string
  latency_ms: number
  chunks_searched: number
}

export interface QueryLog {
  id: string
  query_text: string
  chunks_searched: number
  chunks_returned: number
  top_similarity_score?: number
  invocation_type: 'auto' | 'explicit' | 'ui'
  latency_ms: number
  embedding_cost_usd: string
  created_at: string
}

// ========== API Functions ==========

export const knowledgeApi = {
  // Settings
  getSettings: () =>
    apiClient.get<KnowledgeSettings>('/knowledge/settings/'),

  updateSettings: (data: Partial<KnowledgeSettings>) =>
    apiClient.patch<KnowledgeSettings>('/knowledge/settings/', data),

  // Documents
  listDocuments: () =>
    apiClient.get<KnowledgeDocument[]>('/knowledge/documents/'),

  getDocument: (id: string) =>
    apiClient.get<KnowledgeDocumentDetail>(`/knowledge/documents/${id}/`),

  uploadDocument: (
    file: File,
    tags?: string[],
    onProgress?: (progress: number) => void
  ) => {
    const formData = new FormData()
    formData.append('file', file)
    if (tags?.length) {
      formData.append('tags', JSON.stringify(tags))
    }

    return apiClient.post<KnowledgeDocumentDetail>('/knowledge/documents/', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      onUploadProgress: (progressEvent) => {
        if (progressEvent.total && onProgress) {
          const progress = Math.round((progressEvent.loaded / progressEvent.total) * 100)
          onProgress(progress)
        }
      },
    })
  },

  deleteDocument: (id: string) =>
    apiClient.delete(`/knowledge/documents/${id}/`),

  bulkDeleteDocuments: (ids: string[]) =>
    apiClient.post<{ deleted: number }>('/knowledge/documents/bulk_delete/', { document_ids: ids }),

  reprocessDocument: (id: string) =>
    apiClient.post<{ status: string }>(`/knowledge/documents/${id}/reprocess/`),

  updateDocumentTags: (id: string, tags: string[]) =>
    apiClient.patch<{ tags: string[] }>(`/knowledge/documents/${id}/tags/`, { tags }),

  // Search
  search: (params: {
    query: string
    max_results?: number
    similarity_threshold?: number
    document_ids?: string[]
  }) =>
    apiClient.post<SearchResponse>('/knowledge/search/', params),

  // Query logs
  getQueryLogs: () =>
    apiClient.get<QueryLog[]>('/knowledge/logs/'),

  /**
   * Download document as binary blob.
   * Pattern follows assetsAPI.download() in assets.ts.
   */
  downloadDocument: async (docId: string): Promise<Blob | null> => {
    try {
      const response = await apiClient.get(
        `/knowledge/documents/${docId}/download/`,
        { responseType: 'blob' }
      )
      return response.data
    } catch (error) {
      console.error('[knowledgeApi] Download failed:', error)
      return null
    }
  },
}

export default knowledgeApi
