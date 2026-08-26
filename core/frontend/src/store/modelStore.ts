import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { ModelCatalogEntry, ModelFilter, ModelFavorite, RecentModel } from '../types/models'
import { openRouterApi } from '../api/endpoints'
import { createUserScopedStorage } from '../lib/userScopedStorage'
import { preferencesSync } from '../lib/preferencesSync'
import { PREFERENCE_KEYS } from '../hooks/usePreferencesLoader'

export interface ModelStore {
  // State
  models: ModelCatalogEntry[]
  loading: boolean
  error: string | null
  filter: ModelFilter
  favorites: ModelFavorite[]
  recentModels: RecentModel[]
  recentChatModels: RecentModel[]
  selectedModels: Set<string>
  comparisonModels: ModelCatalogEntry[]
  currentModel: ModelCatalogEntry | null

  // All models state (for Command Palette - loads all pages)
  allModels: ModelCatalogEntry[]
  allModelsLoading: boolean
  allModelsLoaded: boolean

  // Pagination state
  currentPage: number
  totalPages: number
  totalCount: number
  pageSize: number
  currentFilters: ModelFilter  // Store current applied filters
  providerCounts: Record<string, number>  // Count of models per provider
  lastFetchTime: number  // Timestamp of last fetch for cache invalidation
  lastFetchedPage: number  // Page that was actually fetched (for cache comparison)

  // Hydration state
  _hasHydrated: boolean

  // Actions
  fetchModels: (page?: number, filters?: ModelFilter, forceRefresh?: boolean) => Promise<void>
  fetchAllModels: () => Promise<void>
  setFilter: (filter: Partial<ModelFilter>) => void
  clearFilter: () => void
  addFavorite: (modelId: string, details?: ModelCatalogEntry, notes?: string) => void
  removeFavorite: (modelId: string) => void
  reorderFavorites: (newOrder: string[]) => void
  addRecentModel: (modelId: string, details?: ModelCatalogEntry) => void
  addRecentChatModel: (modelId: string, details?: ModelCatalogEntry) => void
  toggleModelSelection: (modelId: string) => void
  clearSelection: () => void
  addToComparison: (model: ModelCatalogEntry) => void
  removeFromComparison: (modelId: string) => void
  clearComparison: () => void
  setCurrentPage: (page: number) => void
  setCurrentModel: (model: ModelCatalogEntry | null) => void
  setDefaultModelIfNeeded: () => Promise<void>
}

const MAX_RECENT_MODELS = 10
const MAX_RECENT_CHAT_MODELS = 5
const MAX_COMPARISON_MODELS = 5

// Default model for new users — Sterna auto-router
const DEFAULT_MODEL_ID = 'ornithops/sterna'

const useModelStore = create<ModelStore>()(
  persist(
    (set, get) => ({
      // Initial state
      models: [],
      loading: false,
      error: null,
      filter: {},
      favorites: [],
      recentModels: [],
      recentChatModels: [],
      selectedModels: new Set(),
      comparisonModels: [],
      currentModel: null,

      // All models state
      allModels: [],
      allModelsLoading: false,
      allModelsLoaded: false,

      // Pagination state
      currentPage: 1,
      totalPages: 1,
      totalCount: 0,
      pageSize: 20,
      currentFilters: {},
      providerCounts: {},
      lastFetchTime: 0,
      lastFetchedPage: 0,

      // Hydration state
      _hasHydrated: false,

      // Fetch models from API
      fetchModels: async (page = 1, filters?: ModelFilter, forceRefresh = false) => {
        const state = get()
        const appliedFilters = filters !== undefined ? filters : state.currentFilters

        // Cache validity: 5 minutes
        const CACHE_TTL = 5 * 60 * 1000
        const isCacheValid = Date.now() - state.lastFetchTime < CACHE_TTL
        const filtersMatch = JSON.stringify(appliedFilters) === JSON.stringify(state.currentFilters)
        const pageMatch = page === state.lastFetchedPage
        const hasModels = state.models.length > 0

        // Use cached data if valid and matches request
        if (!forceRefresh && hasModels && isCacheValid && filtersMatch && pageMatch && !state.loading) {
          return
        }

        set({ loading: true, error: null })
        try {

          // Build params object for API call
          // Always filter to only show models that support tool calls
          const params: NonNullable<Parameters<typeof openRouterApi.models>[0]> = { page, supports_functions: true }
          if (appliedFilters.search) params.search = appliedFilters.search
          if (appliedFilters.provider) params.provider = appliedFilters.provider
          if (appliedFilters.minContextLength) params.min_context_length = appliedFilters.minContextLength
          if (appliedFilters.availableOnly !== undefined) {
            params.available_only = appliedFilters.availableOnly
          }
          if (appliedFilters.priceRange) {
            params.min_price = appliedFilters.priceRange.min
            params.max_price = appliedFilters.priceRange.max
          }
          if (appliedFilters.capabilities?.streaming !== undefined) {
            params.supports_streaming = appliedFilters.capabilities.streaming
          }
          // Note: supports_functions is always true (set above), user filter is ignored
          if (appliedFilters.capabilities?.structured_outputs !== undefined) {
            params.supports_structured_outputs = appliedFilters.capabilities.structured_outputs
          }
          if (appliedFilters.capabilities?.reasoning !== undefined) {
            params.supports_reasoning = appliedFilters.capabilities.reasoning
          }
          if (appliedFilters.capabilities?.prompt_caching !== undefined) {
            params.supports_prompt_caching = appliedFilters.capabilities.prompt_caching
          }
          if (appliedFilters.capabilities?.stream_cancellation !== undefined) {
            params.supports_stream_cancellation = appliedFilters.capabilities.stream_cancellation
          }
          if (appliedFilters.input_modalities && appliedFilters.input_modalities.length > 0) {
            // Convert array to comma-separated string for HTTP query params
            params.input_modalities = appliedFilters.input_modalities.join(',')
          }
          if (appliedFilters.tags && appliedFilters.tags.length > 0) {
            params.tags = appliedFilters.tags
          }
          if (appliedFilters.sortBy) params.sort_by = appliedFilters.sortBy
          if (appliedFilters.order) params.order = appliedFilters.order

          const response = await openRouterApi.models(params)
          const { results, count, provider_counts } = response.data
          const totalPages = Math.ceil(count / get().pageSize)

          set({
            models: results || [],
            currentPage: page,
            totalPages,
            totalCount: count || 0,
            providerCounts: provider_counts || {},
            loading: false,
            currentFilters: appliedFilters,
            lastFetchTime: Date.now(),
            lastFetchedPage: page,
          })
        } catch (error) {
          set({
            error: error instanceof Error ? error.message : 'Failed to fetch models',
            loading: false,
          })
        }
      },

      // Fetch all models (all pages) - for Command Palette
      fetchAllModels: async () => {
        const state = get()

        // Skip if already loaded or currently loading
        if (state.allModelsLoaded || state.allModelsLoading) {
          return
        }

        set({ allModelsLoading: true, error: null })

        try {
          // First, fetch page 1 to get total count
          // Always filter to only show models that support tool calls
          const firstPageResponse = await openRouterApi.models({ page: 1, supports_functions: true })
          const { results: firstPageResults, count } = firstPageResponse.data
          const totalPages = Math.ceil(count / state.pageSize)

          // If only 1 page, we're done
          if (totalPages <= 1) {
            set({
              allModels: firstPageResults || [],
              allModelsLoading: false,
              allModelsLoaded: true,
            })
            return
          }

          // Fetch remaining pages in parallel
          const pagePromises = []
          for (let page = 2; page <= totalPages; page++) {
            pagePromises.push(openRouterApi.models({ page, supports_functions: true }))
          }

          const remainingPagesResponses = await Promise.all(pagePromises)

          // Combine all results
          const allModels = [
            ...(firstPageResults || []),
            ...remainingPagesResponses.flatMap(response => response.data.results || [])
          ]

          set({
            allModels,
            allModelsLoading: false,
            allModelsLoaded: true,
          })
        } catch (error) {
          set({
            error: error instanceof Error ? error.message : 'Failed to fetch all models',
            allModelsLoading: false,
          })
        }
      },

      // Filter management
      setFilter: (filter) => {
        set((state) => ({
          filter: { ...state.filter, ...filter },
        }))
      },

      clearFilter: () => {
        set({ filter: {}, currentFilters: {} })
      },

      // Favorites management
      addFavorite: (modelId, details, notes) => {
        set((state) => {
          const newFavorites = [
            ...state.favorites.filter((f) => f.model_id !== modelId),
            {
              model_id: modelId,
              added_at: new Date().toISOString(),
              notes,
              details,  // Store complete model details
            },
          ]

          // Sync to backend
          preferencesSync.update(PREFERENCE_KEYS.MODELS_FAVORITES, newFavorites, 'models')

          return { favorites: newFavorites }
        })
      },

      removeFavorite: (modelId) => {
        set((state) => {
          // Prevent removing the currently selected model
          if (state.currentModel?.model_id === modelId) {
            console.warn('Cannot remove the currently selected model from favorites')
            return state
          }

          const newFavorites = state.favorites.filter((f) => f.model_id !== modelId)

          // Sync to backend
          preferencesSync.update(PREFERENCE_KEYS.MODELS_FAVORITES, newFavorites, 'models')

          return { favorites: newFavorites }
        })
      },

      reorderFavorites: (newOrder) => {
        set((state) => {
          const favMap = new Map(state.favorites.map((f) => [f.model_id, f]))
          const newFavorites = newOrder
            .map((id) => favMap.get(id))
            .filter((f): f is ModelFavorite => f !== undefined)

          // Sync to backend
          preferencesSync.update(PREFERENCE_KEYS.MODELS_FAVORITES, newFavorites, 'models')

          return { favorites: newFavorites }
        })
      },

      // Recent models management
      addRecentModel: (modelId, details) => {
        set((state) => {
          const existing = state.recentModels.find((m) => m.model_id === modelId)
          const updated = existing
            ? {
                ...existing,
                used_at: new Date().toISOString(),
                usage_count: existing.usage_count + 1,
                details: details || existing.details,  // Update details if provided
              }
            : {
                model_id: modelId,
                used_at: new Date().toISOString(),
                usage_count: 1,
                details: details,  // Store details for new entry
              }

          const newRecent = [
            updated,
            ...state.recentModels.filter((m) => m.model_id !== modelId),
          ].slice(0, MAX_RECENT_MODELS)

          // Sync to backend
          preferencesSync.update(PREFERENCE_KEYS.MODELS_RECENT, newRecent, 'models')

          return { recentModels: newRecent }
        })
      },

      // Recent chat models management (specific to /chats page)
      addRecentChatModel: (modelId, details) => {
        set((state) => {
          const existing = state.recentChatModels.find((m) => m.model_id === modelId)
          const updated = existing
            ? {
                ...existing,
                used_at: new Date().toISOString(),
                usage_count: existing.usage_count + 1,
                details: details || existing.details,  // Update details if provided
              }
            : {
                model_id: modelId,
                used_at: new Date().toISOString(),
                usage_count: 1,
                details: details,  // Store details for new entry
              }

          const newRecentChat = [
            updated,
            ...state.recentChatModels.filter((m) => m.model_id !== modelId),
          ].slice(0, MAX_RECENT_CHAT_MODELS)

          // Sync to backend
          preferencesSync.update(PREFERENCE_KEYS.MODELS_RECENT_CHAT, newRecentChat, 'models')

          return { recentChatModels: newRecentChat }
        })
      },

      // Selection management
      toggleModelSelection: (modelId) => {
        set((state) => {
          const newSelection = new Set(state.selectedModels)
          if (newSelection.has(modelId)) {
            newSelection.delete(modelId)
          } else {
            newSelection.add(modelId)
          }
          return { selectedModels: newSelection }
        })
      },

      clearSelection: () => {
        set({ selectedModels: new Set() })
      },

      // Comparison management
      addToComparison: (model) => {
        set((state) => {
          if (state.comparisonModels.length >= MAX_COMPARISON_MODELS) {
            return state
          }
          if (state.comparisonModels.find((m) => m.id === model.id)) {
            return state
          }
          return {
            comparisonModels: [...state.comparisonModels, model],
          }
        })
      },

      removeFromComparison: (modelId) => {
        set((state) => ({
          comparisonModels: state.comparisonModels.filter((m) => m.id !== modelId),
        }))
      },

      clearComparison: () => {
        set({ comparisonModels: [] })
      },

      setCurrentPage: (page) => {
        set({ currentPage: page })
      },

      setCurrentModel: (model) => {
        set({ currentModel: model })

        // Also add to recent models when selecting
        if (model) {
          get().addRecentModel(model.model_id, model)
        }

        // Sync to backend
        preferencesSync.update(PREFERENCE_KEYS.MODELS_CURRENT, model, 'models')
      },

      // Set the default model (Sterna auto-router) if user doesn't have one selected
      setDefaultModelIfNeeded: async () => {
        // Wait for store to finish hydrating from localStorage
        const waitForHydration = async () => {
          if (get()._hasHydrated) return
          const maxWait = 2000
          const interval = 50
          let waited = 0
          while (!get()._hasHydrated && waited < maxWait) {
            await new Promise(resolve => setTimeout(resolve, interval))
            waited += interval
          }
        }

        await waitForHydration()

        // Skip if user already has a model selected
        if (get().currentModel) return

        try {
          // Fetch page 1 of catalog — Sterna is always prepended as the first entry
          const response = await openRouterApi.models({ page: 1 })
          const models = response.data.results || []
          const sterna = models.find((m: ModelCatalogEntry) => m.model_id === DEFAULT_MODEL_ID)

          if (sterna) {
            set({ currentModel: sterna })
            preferencesSync.update(PREFERENCE_KEYS.MODELS_CURRENT, sterna, 'models')
          } else if (models.length > 0) {
            // Fallback if Sterna entry is somehow missing
            set({ currentModel: models[0] })
            preferencesSync.update(PREFERENCE_KEYS.MODELS_CURRENT, models[0], 'models')
          }
        } catch (error) {
          console.error('[ModelStore] Failed to set default model:', error)
        }
      },

    }),
    {
      name: 'model-storage',
      storage: createUserScopedStorage('model-storage'),
      partialize: (state) => ({
        favorites: state.favorites,
        recentModels: state.recentModels,
        recentChatModels: state.recentChatModels,
        currentModel: state.currentModel,
      }),
      onRehydrateStorage: () => {
        // Note: useModelStore doesn't exist yet at this point (store is being created)
        // We can only access it in the callback after rehydration completes
        

        // Return callback that's called after rehydration completes
        return (state, error) => {
          if (error) {
            console.error('[ModelStore] Rehydration error:', error)
          }
          // Set hydrated flag after rehydration completes
          // Use setTimeout to ensure store is fully initialized
          setTimeout(() => {
            useModelStore.setState({ _hasHydrated: true })
            
          }, 0)
        }
      },
    }
  )
)

// Ensure hydration flag is set even if onRehydrateStorage doesn't fire
// This handles the case where localStorage is empty/invalid
if (typeof window !== 'undefined') {
  // Check if already hydrated after a short delay
  setTimeout(() => {
    if (!useModelStore.getState()._hasHydrated) {
      
      useModelStore.setState({ _hasHydrated: true })
    }
  }, 100)
}

export default useModelStore