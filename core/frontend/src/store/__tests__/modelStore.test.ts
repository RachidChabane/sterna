import { describe, it, expect, beforeEach, vi } from 'vitest'
import useModelStore from '@/store/modelStore'
import { openRouterApi } from '@/api/endpoints'
import type { ModelCatalogEntry } from '@/types/models'
import { makeAxiosResponse } from '@/test/axiosMocks'

vi.mock('@/api/endpoints', () => ({
  openRouterApi: {
    models: vi.fn(),
  },
}))

vi.mock('@/lib/preferencesSync', () => ({
  preferencesSync: { update: vi.fn() },
}))

function makeModel(overrides: Partial<ModelCatalogEntry> = {}): ModelCatalogEntry {
  return {
    id: 'id-1',
    model_id: 'openai/gpt-4o',
    name: 'GPT-4o',
    provider: 'openai',
    cost_per_1m_prompt: 1,
    cost_per_1m_completion: 2,
    max_tokens: 128000,
    supports_streaming: true,
    supports_functions: true,
    supports_structured_outputs: true,
    supports_reasoning: false,
    supports_prompt_caching: true,
    supports_stream_cancellation: true,
    modality: null,
    input_modalities: ['text'],
    output_modalities: ['text'],
    tokenizer: null,
    max_completion_tokens: null,
    is_moderated: false,
    default_parameters: {},
    tags: [],
    is_available: true,
    fetched_at: '2026-01-01T00:00:00Z',
    ...overrides,
  }
}

const DEFAULT_MODEL_ID = 'ornithops/sterna'

describe('modelStore', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useModelStore.setState({
      models: [],
      loading: false,
      error: null,
      favorites: [],
      recentModels: [],
      recentChatModels: [],
      selectedModels: new Set(),
      comparisonModels: [],
      currentModel: null,
      allModels: [],
      allModelsLoading: false,
      allModelsLoaded: false,
      currentPage: 1,
      totalPages: 1,
      totalCount: 0,
      currentFilters: {},
      providerCounts: {},
      lastFetchTime: 0,
      lastFetchedPage: 0,
      _hasHydrated: true,
    })
  })

  describe('fetchModels', () => {
    it('fetches page 1 and stores results', async () => {
      const model = makeModel()
      vi.mocked(openRouterApi.models).mockResolvedValue(
        makeAxiosResponse({ results: [model], count: 1, provider_counts: { openai: 1 } })
      )

      await useModelStore.getState().fetchModels()

      const state = useModelStore.getState()
      expect(state.models).toEqual([model])
      expect(state.totalCount).toBe(1)
      expect(state.loading).toBe(false)
    })

    it('skips the API call when a valid cache exists for the same page/filters', async () => {
      useModelStore.setState({
        models: [makeModel()],
        lastFetchTime: Date.now(),
        lastFetchedPage: 1,
        currentFilters: {},
      })

      await useModelStore.getState().fetchModels(1, {})

      expect(openRouterApi.models).not.toHaveBeenCalled()
    })

    it('refetches when forceRefresh is true even with a valid cache', async () => {
      useModelStore.setState({
        models: [makeModel()],
        lastFetchTime: Date.now(),
        lastFetchedPage: 1,
        currentFilters: {},
      })
      vi.mocked(openRouterApi.models).mockResolvedValue(
        makeAxiosResponse({ results: [], count: 0, provider_counts: {} })
      )

      await useModelStore.getState().fetchModels(1, {}, true)

      expect(openRouterApi.models).toHaveBeenCalledTimes(1)
    })

    it('sets an error and stops loading when the request fails', async () => {
      vi.mocked(openRouterApi.models).mockRejectedValue(new Error('network down'))

      await useModelStore.getState().fetchModels()

      const state = useModelStore.getState()
      expect(state.error).toBe('network down')
      expect(state.loading).toBe(false)
    })
  })

  describe('setCurrentModel', () => {
    it('sets the current model and records it as a recent model', () => {
      const model = makeModel()
      useModelStore.getState().setCurrentModel(model)

      const state = useModelStore.getState()
      expect(state.currentModel).toEqual(model)
      expect(state.recentModels[0].model_id).toBe(model.model_id)
      expect(state.recentModels[0].usage_count).toBe(1)
    })

    it('bumps usage_count instead of duplicating an existing recent model entry', () => {
      const model = makeModel()
      useModelStore.getState().setCurrentModel(model)
      useModelStore.getState().addRecentModel(model.model_id, model)

      const state = useModelStore.getState()
      expect(state.recentModels).toHaveLength(1)
      expect(state.recentModels[0].usage_count).toBe(2)
    })

    it('caps recentModels at 10 entries, evicting the oldest', () => {
      for (let i = 0; i < 12; i++) {
        useModelStore.getState().addRecentModel(`provider/model-${i}`)
      }
      const state = useModelStore.getState()
      expect(state.recentModels).toHaveLength(10)
      // Most recent first; oldest two (model-0, model-1) evicted.
      expect(state.recentModels.map(m => m.model_id)).not.toContain('provider/model-0')
      expect(state.recentModels[0].model_id).toBe('provider/model-11')
    })
  })

  describe('favorites', () => {
    it('adds a favorite', () => {
      useModelStore.getState().addFavorite('openai/gpt-4o')
      expect(useModelStore.getState().favorites.map(f => f.model_id)).toContain('openai/gpt-4o')
    })

    it('removes a favorite that is not the current model', () => {
      useModelStore.getState().addFavorite('openai/gpt-4o')
      useModelStore.getState().removeFavorite('openai/gpt-4o')
      expect(useModelStore.getState().favorites).toHaveLength(0)
    })

    it('refuses to remove the currently selected model from favorites', () => {
      const model = makeModel()
      useModelStore.setState({ currentModel: model })
      useModelStore.getState().addFavorite(model.model_id)

      useModelStore.getState().removeFavorite(model.model_id)

      expect(useModelStore.getState().favorites.map(f => f.model_id)).toContain(model.model_id)
    })
  })

  describe('comparisonModels', () => {
    it('adds a model to comparison up to the max of 5', () => {
      for (let i = 0; i < 6; i++) {
        useModelStore.getState().addToComparison(makeModel({ id: `id-${i}`, model_id: `m/${i}` }))
      }
      expect(useModelStore.getState().comparisonModels).toHaveLength(5)
    })

    it('does not add a duplicate model (matched by id) to comparison', () => {
      const model = makeModel()
      useModelStore.getState().addToComparison(model)
      useModelStore.getState().addToComparison(model)
      expect(useModelStore.getState().comparisonModels).toHaveLength(1)
    })
  })

  describe('setDefaultModelIfNeeded', () => {
    it('does nothing when a current model is already set', async () => {
      useModelStore.setState({ currentModel: makeModel() })

      await useModelStore.getState().setDefaultModelIfNeeded()

      expect(openRouterApi.models).not.toHaveBeenCalled()
    })

    it('selects the Sterna auto-router entry when present in the catalog', async () => {
      const sterna = makeModel({ model_id: DEFAULT_MODEL_ID, name: 'Sterna' })
      const other = makeModel({ model_id: 'openai/gpt-4o' })
      vi.mocked(openRouterApi.models).mockResolvedValue(
        makeAxiosResponse({ results: [sterna, other], count: 2 })
      )

      await useModelStore.getState().setDefaultModelIfNeeded()

      expect(useModelStore.getState().currentModel?.model_id).toBe(DEFAULT_MODEL_ID)
    })

    it('falls back to the first catalog entry when Sterna is missing', async () => {
      const other = makeModel({ model_id: 'openai/gpt-4o' })
      vi.mocked(openRouterApi.models).mockResolvedValue(
        makeAxiosResponse({ results: [other], count: 1 })
      )

      await useModelStore.getState().setDefaultModelIfNeeded()

      expect(useModelStore.getState().currentModel?.model_id).toBe('openai/gpt-4o')
    })

    it('leaves currentModel null when the catalog is empty', async () => {
      vi.mocked(openRouterApi.models).mockResolvedValue(makeAxiosResponse({ results: [], count: 0 }))

      await useModelStore.getState().setDefaultModelIfNeeded()

      expect(useModelStore.getState().currentModel).toBeNull()
    })

    it('swallows fetch errors and leaves currentModel null', async () => {
      vi.mocked(openRouterApi.models).mockRejectedValue(new Error('boom'))

      await expect(useModelStore.getState().setDefaultModelIfNeeded()).resolves.toBeUndefined()
      expect(useModelStore.getState().currentModel).toBeNull()
    })
  })

  describe('selection', () => {
    it('toggles a model in and out of selectedModels', () => {
      useModelStore.getState().toggleModelSelection('openai/gpt-4o')
      expect(useModelStore.getState().selectedModels.has('openai/gpt-4o')).toBe(true)

      useModelStore.getState().toggleModelSelection('openai/gpt-4o')
      expect(useModelStore.getState().selectedModels.has('openai/gpt-4o')).toBe(false)
    })

    it('clearSelection empties selectedModels', () => {
      useModelStore.getState().toggleModelSelection('a')
      useModelStore.getState().toggleModelSelection('b')
      useModelStore.getState().clearSelection()
      expect(useModelStore.getState().selectedModels.size).toBe(0)
    })
  })
})
