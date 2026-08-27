import { describe, it, expect, vi } from 'vitest'
import { createModelsProvider } from '../ModelsProvider'
import type { ModelStore } from '@/store/modelStore'
import type { ModelCatalogEntry, ModelFavorite } from '@/types/models'

function makeModel(overrides: Partial<ModelCatalogEntry> = {}): ModelCatalogEntry {
  return {
    id: '1',
    model_id: 'openai/gpt-4',
    name: 'GPT-4',
    provider: 'OpenAI',
    cost_per_1m_prompt: 30,
    cost_per_1m_completion: 60,
    max_tokens: 8192,
    supports_streaming: true,
    supports_functions: true,
    supports_structured_outputs: false,
    supports_reasoning: false,
    supports_prompt_caching: false,
    supports_stream_cancellation: false,
    modality: null,
    input_modalities: ['text'],
    output_modalities: ['text'],
    tokenizer: null,
    max_completion_tokens: null,
    is_moderated: false,
    default_parameters: {},
    tags: [],
    is_available: true,
    fetched_at: '2024-01-01',
    ...overrides,
  }
}

function makeStore(overrides: Partial<ModelStore> = {}): ModelStore {
  return {
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
    allModels: [],
    allModelsLoading: false,
    allModelsLoaded: true,
    currentPage: 1,
    totalPages: 1,
    totalCount: 0,
    pageSize: 20,
    currentFilters: {},
    providerCounts: {},
    lastFetchTime: 0,
    lastFetchedPage: 0,
    _hasHydrated: true,
    fetchModels: vi.fn(),
    fetchAllModels: vi.fn(),
    setFilter: vi.fn(),
    clearFilter: vi.fn(),
    addFavorite: vi.fn(),
    removeFavorite: vi.fn(),
    reorderFavorites: vi.fn(),
    addRecentModel: vi.fn(),
    addRecentChatModel: vi.fn(),
    toggleModelSelection: vi.fn(),
    clearSelection: vi.fn(),
    addToComparison: vi.fn(),
    removeFromComparison: vi.fn(),
    clearComparison: vi.fn(),
    setCurrentPage: vi.fn(),
    setCurrentModel: vi.fn(),
    setDefaultModelIfNeeded: vi.fn(),
    ...overrides,
  }
}

describe('createModelsProvider', () => {
  it('exposes a favorite-toggle and a compare-toggle action per model', async () => {
    const gpt4 = makeModel()
    const store = makeStore({ allModels: [gpt4] })
    const provider = createModelsProvider(() => store)

    const items = await provider.getItems('')

    expect(items).toHaveLength(1)
    const labels = items[0].actions?.map((a) => a.label)
    expect(labels).toEqual(['Add to favorites', 'Add to comparison'])
  })

  it('dispatches addFavorite when favoriting an unfavorited model', async () => {
    const gpt4 = makeModel()
    const store = makeStore({ allModels: [gpt4] })
    const provider = createModelsProvider(() => store)

    const items = await provider.getItems('')
    const favoriteAction = items[0].actions?.find((a) => a.label === 'Add to favorites')
    favoriteAction?.onClick({} as React.MouseEvent)

    expect(store.addFavorite).toHaveBeenCalledWith('openai/gpt-4', gpt4)
    expect(store.removeFavorite).not.toHaveBeenCalled()
  })

  it('dispatches removeFavorite when unfavoriting an already-favorited model', async () => {
    const gpt4 = makeModel()
    const favorite: ModelFavorite = { model_id: 'openai/gpt-4', added_at: '2024-01-01' }
    const store = makeStore({ allModels: [gpt4], favorites: [favorite] })
    const provider = createModelsProvider(() => store)

    const items = await provider.getItems('')
    expect(items[0].isFavorite).toBe(true)
    const favoriteAction = items[0].actions?.find((a) => a.label === 'Remove from favorites')
    favoriteAction?.onClick({} as React.MouseEvent)

    expect(store.removeFavorite).toHaveBeenCalledWith('openai/gpt-4')
    expect(store.addFavorite).not.toHaveBeenCalled()
  })

  it('dispatches addToComparison when adding a model not yet compared', async () => {
    const gpt4 = makeModel()
    const store = makeStore({ allModels: [gpt4] })
    const provider = createModelsProvider(() => store)

    const items = await provider.getItems('')
    const compareAction = items[0].actions?.find((a) => a.label === 'Add to comparison')
    compareAction?.onClick({} as React.MouseEvent)

    expect(store.addToComparison).toHaveBeenCalledWith(gpt4)
    expect(store.removeFromComparison).not.toHaveBeenCalled()
  })

  it('dispatches removeFromComparison by id when removing an already-compared model', async () => {
    const gpt4 = makeModel()
    const store = makeStore({ allModels: [gpt4], comparisonModels: [gpt4] })
    const provider = createModelsProvider(() => store)

    const items = await provider.getItems('')
    const compareAction = items[0].actions?.find((a) => a.label === 'Remove from comparison')
    compareAction?.onClick({} as React.MouseEvent)

    expect(store.removeFromComparison).toHaveBeenCalledWith(gpt4.id)
    expect(store.addToComparison).not.toHaveBeenCalled()
  })

  it('reads favorite state fresh at click time, not from the getItems() snapshot', async () => {
    // The palette does not refetch items between renders, so an item's actions
    // must decide add-vs-remove from the store at click time. Mutate the store
    // after getItems() resolves to prove the closure isn't stuck on the snapshot.
    const gpt4 = makeModel()
    const store = makeStore({ allModels: [gpt4] })
    const provider = createModelsProvider(() => store)

    const items = await provider.getItems('')
    const favoriteAction = items[0].actions?.find((a) => a.label === 'Add to favorites')

    store.favorites = [{ model_id: 'openai/gpt-4', added_at: '2024-01-01' }]
    favoriteAction?.onClick({} as React.MouseEvent)

    expect(store.removeFavorite).toHaveBeenCalledWith('openai/gpt-4')
    expect(store.addFavorite).not.toHaveBeenCalled()
  })

  it('reads comparison state fresh at click time, not from the getItems() snapshot', async () => {
    const gpt4 = makeModel()
    const store = makeStore({ allModels: [gpt4] })
    const provider = createModelsProvider(() => store)

    const items = await provider.getItems('')
    const compareAction = items[0].actions?.find((a) => a.label === 'Add to comparison')

    store.comparisonModels = [gpt4]
    compareAction?.onClick({} as React.MouseEvent)

    expect(store.removeFromComparison).toHaveBeenCalledWith(gpt4.id)
    expect(store.addToComparison).not.toHaveBeenCalled()
  })

  it('dispatches setCurrentModel when the item itself is selected (model switching)', async () => {
    const gpt4 = makeModel()
    const store = makeStore({ allModels: [gpt4] })
    const provider = createModelsProvider(() => store)

    const items = await provider.getItems('')
    items[0].onSelect()

    expect(store.setCurrentModel).toHaveBeenCalledWith(gpt4)
  })
})
