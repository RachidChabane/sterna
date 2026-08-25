/**
 * Zustand store for Knowledge Base state management
 *
 * Manages:
 * - Knowledge base settings
 * - Document list and upload status
 * - Search results
 * - Upload progress tracking
 */

import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import {
  knowledgeApi,
  type KnowledgeDocument,
  type KnowledgeSettings,
  type SearchResult,
  type SearchResponse,
} from '@/api/knowledge'

// Cache TTL: 5 minutes
const CACHE_TTL = 5 * 60 * 1000

interface KnowledgeStore {
  // ========== State ==========

  // Settings
  settings: KnowledgeSettings | null
  settingsLoading: boolean
  settingsError: string | null
  lastSettingsFetchTime: number

  // Documents
  documents: KnowledgeDocument[]
  documentsLoading: boolean
  documentsError: string | null
  lastDocumentsFetchTime: number

  // Upload progress
  uploadProgress: Record<string, number>
  uploadErrors: Record<string, string>

  // Search
  searchResults: SearchResult[]
  searchLoading: boolean
  searchError: string | null
  lastSearchQuery: string
  lastSearchResponse: SearchResponse | null

  // ========== Actions ==========

  // Settings
  fetchSettings: (forceRefresh?: boolean) => Promise<void>
  updateSettings: (settings: Partial<KnowledgeSettings>) => Promise<void>

  // Documents
  fetchDocuments: (forceRefresh?: boolean) => Promise<void>
  uploadDocument: (file: File, tags?: string[]) => Promise<KnowledgeDocument | null>
  deleteDocument: (id: string) => Promise<boolean>
  deleteDocuments: (ids: string[]) => Promise<number>
  reprocessDocument: (id: string) => Promise<boolean>
  updateDocumentTags: (id: string, tags: string[]) => Promise<boolean>

  // Search
  search: (query: string, options?: {
    maxResults?: number
    similarityThreshold?: number
    documentIds?: string[]
  }) => Promise<SearchResult[]>
  clearSearch: () => void

  // Upload progress
  setUploadProgress: (fileId: string, progress: number) => void
  setUploadError: (fileId: string, error: string) => void
  clearUploadProgress: (fileId: string) => void
  clearAllUploads: () => void

  // Polling for document status
  pollDocumentStatus: (documentId: string) => void
  stopPolling: () => void

  // Reset
  reset: () => void
}

// Polling state (outside store to avoid serialization issues)
let pollingIntervals: Record<string, ReturnType<typeof setInterval>> = {}

export const useKnowledgeStore = create<KnowledgeStore>()(
  persist(
    (set, get) => ({
      // ========== Initial State ==========

      settings: null,
      settingsLoading: false,
      settingsError: null,
      lastSettingsFetchTime: 0,

      documents: [],
      documentsLoading: false,
      documentsError: null,
      lastDocumentsFetchTime: 0,

      uploadProgress: {},
      uploadErrors: {},

      searchResults: [],
      searchLoading: false,
      searchError: null,
      lastSearchQuery: '',
      lastSearchResponse: null,

      // ========== Settings Actions ==========

      fetchSettings: async (forceRefresh = false) => {
        const { lastSettingsFetchTime, settingsLoading } = get()

        // Skip if already loading
        if (settingsLoading) return

        // Use cache if valid and not forcing refresh
        if (!forceRefresh && Date.now() - lastSettingsFetchTime < CACHE_TTL && get().settings) {
          return
        }

        set({ settingsLoading: true, settingsError: null })

        try {
          const response = await knowledgeApi.getSettings()
          set({
            settings: response.data,
            settingsLoading: false,
            lastSettingsFetchTime: Date.now(),
          })
        } catch (error) {
          const message = error instanceof Error ? error.message : 'Failed to fetch settings'
          set({ settingsLoading: false, settingsError: message })
        }
      },

      updateSettings: async (updates) => {
        try {
          const response = await knowledgeApi.updateSettings(updates)
          set({ settings: response.data })
        } catch (error) {
          const message = error instanceof Error ? error.message : 'Failed to update settings'
          set({ settingsError: message })
          throw error
        }
      },

      // ========== Document Actions ==========

      fetchDocuments: async (forceRefresh = false) => {
        const { lastDocumentsFetchTime, documentsLoading } = get()

        if (documentsLoading) return

        if (!forceRefresh && Date.now() - lastDocumentsFetchTime < CACHE_TTL && get().documents.length > 0) {
          return
        }

        set({ documentsLoading: true, documentsError: null })

        try {
          const response = await knowledgeApi.listDocuments()
          set({
            documents: response.data,
            documentsLoading: false,
            lastDocumentsFetchTime: Date.now(),
          })
        } catch (error) {
          const message = error instanceof Error ? error.message : 'Failed to fetch documents'
          set({ documentsLoading: false, documentsError: message })
        }
      },

      uploadDocument: async (file, tags) => {
        const fileId = `${file.name}-${Date.now()}`

        set((state) => ({
          uploadProgress: { ...state.uploadProgress, [fileId]: 0 },
        }))

        try {
          const response = await knowledgeApi.uploadDocument(file, tags, (progress) => {
            set((state) => ({
              uploadProgress: { ...state.uploadProgress, [fileId]: progress },
            }))
          })

          const document = response.data

          // Add to documents list
          set((state) => ({
            documents: [document, ...state.documents],
          }))

          // Start polling for status if not ready
          if (document.status !== 'ready' && document.status !== 'failed') {
            get().pollDocumentStatus(document.id)
          }

          // Clear progress after delay
          setTimeout(() => {
            get().clearUploadProgress(fileId)
          }, 1000)

          // Refresh settings to get updated storage stats
          get().fetchSettings(true)

          return document
        } catch (error: unknown) {
          let message = 'Upload failed'
          if (error && typeof error === 'object' && 'response' in error) {
            const axiosError = error as { response?: { data?: { error?: string } } }
            message = axiosError.response?.data?.error || message
          }
          set((state) => ({
            uploadErrors: { ...state.uploadErrors, [fileId]: message },
          }))
          return null
        }
      },

      deleteDocument: async (id) => {
        try {
          await knowledgeApi.deleteDocument(id)
          set((state) => ({
            documents: state.documents.filter((d) => d.id !== id),
          }))
          // Refresh settings to get updated storage stats
          get().fetchSettings(true)
          return true
        } catch {
          return false
        }
      },

      deleteDocuments: async (ids) => {
        try {
          const response = await knowledgeApi.bulkDeleteDocuments(ids)
          set((state) => ({
            documents: state.documents.filter((d) => !ids.includes(d.id)),
          }))
          get().fetchSettings(true)
          return response.data.deleted
        } catch {
          return 0
        }
      },

      reprocessDocument: async (id) => {
        try {
          await knowledgeApi.reprocessDocument(id)
          // Update document status locally
          set((state) => ({
            documents: state.documents.map((d) =>
              d.id === id ? { ...d, status: 'pending' as const } : d
            ),
          }))
          // Start polling for status
          get().pollDocumentStatus(id)
          return true
        } catch {
          return false
        }
      },

      updateDocumentTags: async (id, tags) => {
        try {
          await knowledgeApi.updateDocumentTags(id, tags)
          set((state) => ({
            documents: state.documents.map((d) =>
              d.id === id ? { ...d, tags } : d
            ),
          }))
          return true
        } catch {
          return false
        }
      },

      // ========== Search Actions ==========

      search: async (query, options = {}) => {
        set({ searchLoading: true, searchError: null, lastSearchQuery: query })

        try {
          const response = await knowledgeApi.search({
            query,
            max_results: options.maxResults ?? 5,
            similarity_threshold: options.similarityThreshold,
            document_ids: options.documentIds,
          })

          set({
            searchResults: response.data.results,
            searchLoading: false,
            lastSearchResponse: response.data,
          })

          return response.data.results
        } catch (error) {
          const message = error instanceof Error ? error.message : 'Search failed'
          set({ searchLoading: false, searchError: message })
          return []
        }
      },

      clearSearch: () => {
        set({
          searchResults: [],
          lastSearchQuery: '',
          lastSearchResponse: null,
          searchError: null,
        })
      },

      // ========== Upload Progress Actions ==========

      setUploadProgress: (fileId, progress) => {
        set((state) => ({
          uploadProgress: { ...state.uploadProgress, [fileId]: progress },
        }))
      },

      setUploadError: (fileId, error) => {
        set((state) => ({
          uploadErrors: { ...state.uploadErrors, [fileId]: error },
        }))
      },

      clearUploadProgress: (fileId) => {
        set((state) => {
          const { [fileId]: _progress, ...restProgress } = state.uploadProgress
          const { [fileId]: _error, ...restErrors } = state.uploadErrors
          return {
            uploadProgress: restProgress,
            uploadErrors: restErrors,
          }
        })
      },

      clearAllUploads: () => {
        set({ uploadProgress: {}, uploadErrors: {} })
      },

      // ========== Polling Actions ==========

      pollDocumentStatus: (documentId) => {
        // Clear any existing polling for this document
        if (pollingIntervals[documentId]) {
          clearInterval(pollingIntervals[documentId])
        }

        // Poll every 2 seconds
        pollingIntervals[documentId] = setInterval(async () => {
          try {
            const response = await knowledgeApi.getDocument(documentId)
            const updatedDoc = response.data

            set((state) => ({
              documents: state.documents.map((d) =>
                d.id === documentId ? { ...d, ...updatedDoc } : d
              ),
            }))

            // Stop polling when processing is complete
            if (updatedDoc.status === 'ready' || updatedDoc.status === 'failed') {
              clearInterval(pollingIntervals[documentId])
              delete pollingIntervals[documentId]

              // Refresh settings to get updated stats
              get().fetchSettings(true)
            }
          } catch {
            // Stop polling on error
            clearInterval(pollingIntervals[documentId])
            delete pollingIntervals[documentId]
          }
        }, 2000)
      },

      stopPolling: () => {
        Object.keys(pollingIntervals).forEach((id) => {
          clearInterval(pollingIntervals[id])
        })
        pollingIntervals = {}
      },

      // ========== Reset ==========

      reset: () => {
        get().stopPolling()
        set({
          settings: null,
          settingsLoading: false,
          settingsError: null,
          lastSettingsFetchTime: 0,
          documents: [],
          documentsLoading: false,
          documentsError: null,
          lastDocumentsFetchTime: 0,
          uploadProgress: {},
          uploadErrors: {},
          searchResults: [],
          searchLoading: false,
          searchError: null,
          lastSearchQuery: '',
          lastSearchResponse: null,
        })
      },
    }),
    {
      name: 'knowledge-store',
      version: 2, // Bump version to invalidate old cached data
      partialize: () => ({
        // Don't persist any state - always fetch fresh on page load
        // This prevents stale data issues after logout/login
      }),
    }
  )
)
