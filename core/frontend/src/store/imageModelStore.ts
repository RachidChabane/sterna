import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { ImageModelCatalogEntry, ImageModelFilter, ImageModelFavorite } from '../types/models'
import { imageModelsApi } from '../api/endpoints'
import { createUserScopedStorage } from '../lib/userScopedStorage'

interface ImageModelStore {
  // State
  models: ImageModelCatalogEntry[]
  loading: boolean
  error: string | null
  filter: ImageModelFilter
  favorites: ImageModelFavorite[]
  currentModel: ImageModelCatalogEntry | null

  // Pagination state
  currentPage: number
  totalPages: number
  totalCount: number
  pageSize: number
  currentFilters: ImageModelFilter

  // Actions
  fetchModels: (page?: number, filters?: ImageModelFilter) => Promise<void>
  setFilter: (filter: Partial<ImageModelFilter>) => void
  clearFilter: () => void
  addFavorite: (modelId: string, details?: ImageModelCatalogEntry, notes?: string) => void
  removeFavorite: (modelId: string) => void
  setCurrentModel: (model: ImageModelCatalogEntry | null) => void
  refreshCatalog: () => Promise<void>
}

const useImageModelStore = create<ImageModelStore>()(
  persist(
    (set, get) => ({
      // Initial state
      models: [],
      loading: false,
      error: null,
      filter: {},
      favorites: [],
      currentModel: null,

      // Pagination state
      currentPage: 1,
      totalPages: 1,
      totalCount: 0,
      pageSize: 20,
      currentFilters: {},

      // Fetch models from API
      fetchModels: async (page = 1, filters?: ImageModelFilter) => {
        set({ loading: true, error: null })
        try {
          // Use provided filters or keep current filters
          const appliedFilters = filters !== undefined ? filters : get().currentFilters

          // Build params object for API call
          const params: any = { page }
          if (appliedFilters.search) params.search = appliedFilters.search
          if (appliedFilters.provider) params.provider = appliedFilters.provider
          if (appliedFilters.availableOnly !== undefined) {
            params.available_only = appliedFilters.availableOnly
          }
          if (appliedFilters.supports_editing !== undefined) {
            params.supports_editing = appliedFilters.supports_editing
          }
          if (appliedFilters.supports_variations !== undefined) {
            params.supports_variations = appliedFilters.supports_variations
          }
          if (appliedFilters.best_for_text !== undefined) {
            params.best_for_text = appliedFilters.best_for_text
          }
          if (appliedFilters.best_for_photorealism !== undefined) {
            params.best_for_photorealism = appliedFilters.best_for_photorealism
          }
          if (appliedFilters.is_fast !== undefined) {
            params.is_fast = appliedFilters.is_fast
          }
          if (appliedFilters.maxPrice !== undefined) {
            params.max_price = appliedFilters.maxPrice
          }
          if (appliedFilters.sortBy) params.sort_by = appliedFilters.sortBy
          if (appliedFilters.order) params.order = appliedFilters.order

          const response = await imageModelsApi.list(params)
          const { results, count } = response.data
          const totalPages = Math.ceil(count / get().pageSize)

          set({
            models: results || [],
            currentPage: page,
            totalPages,
            totalCount: count || 0,
            loading: false,
            currentFilters: appliedFilters
          })
        } catch (error) {
          set({
            error: error instanceof Error ? error.message : 'Failed to fetch image models',
            loading: false,
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
              details,
            },
          ]
          return { favorites: newFavorites }
        })
      },

      removeFavorite: (modelId) => {
        set((state) => ({
          favorites: state.favorites.filter((f) => f.model_id !== modelId),
        }))
      },

      setCurrentModel: (model) => {
        set({ currentModel: model })
      },

      refreshCatalog: async () => {
        set({ loading: true, error: null })
        try {
          await imageModelsApi.refresh()
          // Re-fetch models after refresh
          await get().fetchModels(1, {})
        } catch (error) {
          set({
            error: error instanceof Error ? error.message : 'Failed to refresh catalog',
            loading: false,
          })
        }
      },
    }),
    {
      name: 'image-model-storage',
      storage: createUserScopedStorage('image-model-storage'),
      partialize: (state) => ({
        favorites: state.favorites,
        currentModel: state.currentModel,
      }),
    }
  )
)

export default useImageModelStore
