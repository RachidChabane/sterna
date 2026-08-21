import { render, screen, fireEvent, within } from '@testing-library/react'
import { vi, describe, it, expect, beforeEach, type Mock } from 'vitest'
import { ModelCatalogBrowser } from '../ModelCatalogBrowser'
import useModelStore from '@/store/modelStore'
import type { ModelCatalogEntry } from '@/types/models'

// The component reads the whole store via `useModelStore()` (no selector),
// so mocking the default export as a fn returning a plain object is accurate.
vi.mock('@/store/modelStore', () => ({
  default: vi.fn(),
}))

const mockedUseModelStore = useModelStore as unknown as Mock

/**
 * The component formats numbers with toLocaleString(), whose output depends on
 * the ICU locale of the test process (e.g. "8,192" vs "8 192"). Build expected
 * strings with the same formatter and collapse all whitespace variants the way
 * testing-library's default normalizer does.
 */
const norm = (s: string) => s.replace(/\s+/g, ' ')
const localized = (n: number) => norm(n.toLocaleString())

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
    description: 'Latest GPT-4 model',
    tags: [],
    is_available: true,
    fetched_at: '2024-01-01',
    ...overrides,
  }
}

describe('ModelCatalogBrowser', () => {
  const gpt4 = makeModel({
    id: '1',
    model_id: 'openai/gpt-4',
    name: 'GPT-4',
    provider: 'OpenAI',
    supports_functions: true,
    tags: ['chat', 'reasoning'],
  })
  const claude = makeModel({
    id: '2',
    model_id: 'anthropic/claude-3',
    name: 'Claude 3',
    provider: 'Anthropic',
    cost_per_1m_prompt: 8,
    cost_per_1m_completion: 24,
    max_tokens: 100000,
    supports_reasoning: true,
    tags: ['long-context'],
  })
  const llama = makeModel({
    id: '3',
    model_id: 'meta/llama-2',
    name: 'Llama 2',
    provider: 'Meta',
    cost_per_1m_prompt: 0.1,
    cost_per_1m_completion: 0.1,
    max_tokens: 4096,
    supports_functions: false,
    tags: ['open-source'],
  })
  const mockModels = [gpt4, claude, llama]

  function createStore(overrides: Record<string, unknown> = {}) {
    return {
      models: mockModels,
      loading: false,
      error: null,
      filter: {},
      favorites: [],
      recentModels: [],
      fetchModels: vi.fn(),
      fetchAllModels: vi.fn(),
      allModels: [],
      allModelsLoading: false,
      allModelsLoaded: false,
      addFavorite: vi.fn(),
      removeFavorite: vi.fn(),
      addToComparison: vi.fn(),
      removeFromComparison: vi.fn(),
      comparisonModels: [] as ModelCatalogEntry[],
      currentPage: 1,
      totalPages: 1,
      totalCount: 3,
      providerCounts: { OpenAI: 1, Anthropic: 1, Meta: 1 },
      setCurrentPage: vi.fn(),
      setCurrentModel: vi.fn(),
      ...overrides,
    }
  }

  let store: ReturnType<typeof createStore>

  beforeEach(() => {
    vi.clearAllMocks()
    store = createStore()
    mockedUseModelStore.mockImplementation(() => store)
  })

  /** Buttons whose content is a given lucide icon (icon-only buttons have no name). */
  function buttonsWithIcon(iconClass: string): HTMLButtonElement[] {
    return Array.from(document.querySelectorAll('button')).filter((btn) =>
      btn.querySelector(`svg.${iconClass}`)
    ) as HTMLButtonElement[]
  }

  it('renders all models from the store', () => {
    render(<ModelCatalogBrowser />)

    // Each model renders once as a mobile card and once as a desktop card
    expect(screen.getAllByText('GPT-4').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Claude 3').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Llama 2').length).toBeGreaterThan(0)
  })

  it('fetches page 1 on mount with the store filter and current sort', () => {
    render(<ModelCatalogBrowser />)

    expect(store.fetchModels).toHaveBeenCalledTimes(1)
    expect(store.fetchModels).toHaveBeenCalledWith(
      1,
      expect.objectContaining({ order: 'asc' })
    )
    // Default sort is 'none' which is sent as undefined
    expect(store.fetchModels.mock.calls[0][1].sortBy).toBeUndefined()
  })

  it('passes an explicit external sort to fetchModels', () => {
    render(<ModelCatalogBrowser sortBy="prompt_cost" sortOrder="desc" />)

    expect(store.fetchModels).toHaveBeenCalledWith(
      1,
      expect.objectContaining({ sortBy: 'prompt_cost', order: 'desc' })
    )
  })

  it('shows loading state when loading', () => {
    store = createStore({ loading: true })
    mockedUseModelStore.mockImplementation(() => store)

    render(<ModelCatalogBrowser />)
    expect(screen.getByText('Loading models...')).toBeInTheDocument()
  })

  it('shows error state when there is an error', () => {
    const errorMessage = 'Failed to fetch models'
    store = createStore({ error: errorMessage })
    mockedUseModelStore.mockImplementation(() => store)

    render(<ModelCatalogBrowser />)
    expect(screen.getByText(errorMessage)).toBeInTheDocument()
  })

  it('shows an empty state when no models match', () => {
    store = createStore({ models: [] })
    mockedUseModelStore.mockImplementation(() => store)

    render(<ModelCatalogBrowser />)
    expect(screen.getByText('No models found')).toBeInTheDocument()
    expect(
      screen.getByText('Try adjusting your filters or search criteria')
    ).toBeInTheDocument()
  })

  it('groups models by provider with model counts when unsorted', () => {
    render(<ModelCatalogBrowser />)

    const openAiHeading = screen.getByRole('heading', { name: /OpenAI/ })
    expect(openAiHeading).toBeInTheDocument()
    expect(within(openAiHeading).getByText('1 model')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: /Anthropic/ })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: /Meta/ })).toBeInTheDocument()
  })

  it('uses providerCounts from the store for group badges', () => {
    store = createStore({ providerCounts: { OpenAI: 12, Anthropic: 1, Meta: 1 } })
    mockedUseModelStore.mockImplementation(() => store)

    render(<ModelCatalogBrowser />)

    const openAiHeading = screen.getByRole('heading', { name: /OpenAI/ })
    expect(within(openAiHeading).getByText('12 models')).toBeInTheDocument()
  })

  it('renders a flat (ungrouped) list when a cost sort is active', () => {
    render(<ModelCatalogBrowser sortBy="prompt_cost" sortOrder="asc" />)

    // No provider group headings in sorted mode
    expect(screen.queryByRole('heading', { name: /OpenAI/ })).not.toBeInTheDocument()
    // Models still render
    expect(screen.getAllByText('GPT-4').length).toBeGreaterThan(0)
  })

  it('selects a model via the Select button', () => {
    const onSelectModel = vi.fn()
    render(<ModelCatalogBrowser onSelectModel={onSelectModel} />)

    // First provider group is OpenAI, so the first Select button belongs to GPT-4
    const selectButtons = screen.getAllByRole('button', { name: 'Select' })
    fireEvent.click(selectButtons[0])

    expect(store.setCurrentModel).toHaveBeenCalledWith(gpt4)
    expect(onSelectModel).toHaveBeenCalledWith(gpt4)
  })

  it('shows the selected indicator for the selected model', () => {
    render(<ModelCatalogBrowser selectedModelId="openai/gpt-4" />)

    // Desktop card shows a "Selected" badge and the select button reads "Selected"
    expect(screen.getAllByText('Selected').length).toBeGreaterThan(0)
  })

  it('adds a model to favorites when its star button is clicked', () => {
    render(<ModelCatalogBrowser />)

    // DOM order: OpenAI group first, mobile card first — its star is GPT-4's
    const starButtons = buttonsWithIcon('lucide-star')
    expect(starButtons.length).toBeGreaterThan(0)
    fireEvent.click(starButtons[0])

    expect(store.addFavorite).toHaveBeenCalledWith('openai/gpt-4', gpt4)
    expect(store.removeFavorite).not.toHaveBeenCalled()
  })

  it('removes a favorited model and shows the filled star indicator', () => {
    store = createStore({
      favorites: [{ model_id: 'openai/gpt-4', added_at: '2024-01-01' }],
    })
    mockedUseModelStore.mockImplementation(() => store)

    render(<ModelCatalogBrowser />)

    const filledStars = document.querySelectorAll('svg.lucide-star.fill-yellow-500')
    expect(filledStars.length).toBeGreaterThan(0)

    const starButtons = buttonsWithIcon('lucide-star')
    fireEvent.click(starButtons[0])

    expect(store.removeFavorite).toHaveBeenCalledWith('openai/gpt-4')
    expect(store.addFavorite).not.toHaveBeenCalled()
  })

  it('adds a model to comparison via the Compare button', () => {
    render(<ModelCatalogBrowser />)

    const compareButtons = screen.getAllByRole('button', { name: 'Compare' })
    fireEvent.click(compareButtons[0])

    expect(store.addToComparison).toHaveBeenCalledWith(gpt4)
  })

  it('removes a model already in comparison', () => {
    store = createStore({ comparisonModels: [gpt4] })
    mockedUseModelStore.mockImplementation(() => store)

    render(<ModelCatalogBrowser />)

    const inComparisonButtons = screen.getAllByRole('button', { name: 'In Comparison' })
    fireEvent.click(inComparisonButtons[0])

    expect(store.removeFromComparison).toHaveBeenCalledWith(gpt4.id)
  })

  it('disables Compare buttons when the comparison is full (5 models)', () => {
    const fullComparison = Array.from({ length: 5 }, (_, i) =>
      makeModel({ id: `c${i}`, model_id: `other/model-${i}`, name: `Other ${i}` })
    )
    store = createStore({ comparisonModels: fullComparison })
    mockedUseModelStore.mockImplementation(() => store)

    render(<ModelCatalogBrowser />)

    const compareButtons = screen.getAllByRole('button', { name: 'Compare' })
    compareButtons.forEach((btn) => expect(btn).toBeDisabled())
  })

  it('hides comparison controls when showComparison is false', () => {
    render(<ModelCatalogBrowser showComparison={false} />)

    expect(screen.queryByRole('button', { name: 'Compare' })).not.toBeInTheDocument()
  })

  it('displays per-model pricing badges', () => {
    render(<ModelCatalogBrowser />)

    expect(screen.getByText('Prompt: $30.00/1M')).toBeInTheDocument()
    expect(screen.getByText('Completion: $60.00/1M')).toBeInTheDocument()
    expect(screen.getByText('Prompt: $8.00/1M')).toBeInTheDocument()
  })

  it('shows max token badges and capability badges', () => {
    render(<ModelCatalogBrowser />)

    expect(screen.getByText(`Max: ${localized(8192)} tokens`)).toBeInTheDocument()
    expect(screen.getByText(`Max: ${localized(100000)} tokens`)).toBeInTheDocument()
    // gpt4 supports functions -> "Tools"; claude supports reasoning -> "Reasoning"
    expect(screen.getAllByText('Tools').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Reasoning').length).toBeGreaterThan(0)
  })

  it('displays model tags on desktop cards', () => {
    render(<ModelCatalogBrowser />)

    expect(screen.getByText('chat')).toBeInTheDocument()
    expect(screen.getByText('long-context')).toBeInTheDocument()
    expect(screen.getByText('open-source')).toBeInTheDocument()
  })

  it('marks recently added models with a New badge', () => {
    store = createStore({
      models: [makeModel({ first_seen_at: new Date().toISOString() })],
      providerCounts: { OpenAI: 1 },
    })
    mockedUseModelStore.mockImplementation(() => store)

    render(<ModelCatalogBrowser />)

    expect(screen.getAllByText('New').length).toBeGreaterThan(0)
  })

  it('renders pagination and navigates pages', () => {
    store = createStore({ totalPages: 3, totalCount: 50, currentPage: 1 })
    mockedUseModelStore.mockImplementation(() => store)

    render(<ModelCatalogBrowser />)

    expect(screen.getByText('Showing 1-20 of 50 models')).toBeInTheDocument()

    fireEvent.click(screen.getByLabelText('Go to next page'))
    expect(store.setCurrentPage).toHaveBeenCalledWith(2)

    // Previous is a no-op on the first page
    store.setCurrentPage.mockClear()
    fireEvent.click(screen.getByLabelText('Go to previous page'))
    expect(store.setCurrentPage).not.toHaveBeenCalled()
  })

  it('hides pagination when there is a single page', () => {
    render(<ModelCatalogBrowser />)

    expect(screen.queryByLabelText('Go to next page')).not.toBeInTheDocument()
  })

  it('loads the full catalog instead of pages when noPagination is set', () => {
    store = createStore({
      models: [],
      allModels: [llama],
      allModelsLoaded: false,
      totalPages: 5,
      totalCount: 90,
    })
    mockedUseModelStore.mockImplementation(() => store)

    render(<ModelCatalogBrowser noPagination />)

    expect(store.fetchAllModels).toHaveBeenCalled()
    expect(store.fetchModels).not.toHaveBeenCalled()
    // Displays allModels, not the paginated list
    expect(screen.getAllByText('Llama 2').length).toBeGreaterThan(0)
    // Pagination is hidden even with many pages
    expect(screen.queryByLabelText('Go to next page')).not.toBeInTheDocument()
  })
})
