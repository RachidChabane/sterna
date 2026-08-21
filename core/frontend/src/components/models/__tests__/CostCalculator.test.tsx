import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'
import { vi, describe, it, expect, beforeEach, type Mock } from 'vitest'
import type { AxiosResponse } from 'axios'
import { CostCalculator } from '../CostCalculator'
import useModelStore from '@/store/modelStore'
import { llmApi, type Model, type ModelsResponse } from '@/api/llm'
import type { ModelCatalogEntry } from '@/types/models'
import { pricingUtils } from '@/lib/pricing-utils'

// CostCalculator fetches its own models via llmApi.models (paginated).
vi.mock('@/api/llm', () => ({
  llmApi: {
    models: vi.fn(),
  },
}))

// CostCalculator reads { comparisonModels } and the embedded ModelComboBox
// reads { favorites, addFavorite, removeFavorite } — both via whole-store calls.
vi.mock('@/store/modelStore', () => ({
  default: vi.fn(),
}))

const mockedUseModelStore = useModelStore as unknown as Mock
const mockedModels = vi.mocked(llmApi.models)

/**
 * Locale-independent expectations: the component formats some numbers with
 * toLocaleString(), whose output depends on the test process ICU locale.
 * Build expected strings through the same code paths and collapse whitespace
 * the way testing-library's default normalizer does.
 */
const norm = (s: string) => s.replace(/\s+/g, ' ')
const localized = (n: number) => norm(n.toLocaleString())
const fmtCost = (n: number) => norm(pricingUtils.formatCostDisplay(n))

function makeRawModel(overrides: Partial<Model> = {}): Model {
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
    input_modalities: ['text'],
    output_modalities: ['text'],
    tags: [],
    is_available: true,
    ...overrides,
  }
}

function makeEntry(overrides: Partial<ModelCatalogEntry> = {}): ModelCatalogEntry {
  return {
    modality: null,
    tokenizer: null,
    max_completion_tokens: null,
    is_moderated: false,
    default_parameters: {},
    fetched_at: '2024-01-01',
    ...makeRawModel(),
    tags: [],
    output_modalities: ['text'],
    ...overrides,
  }
}

const pageResponse = (results: Model[], count = results.length) =>
  ({
    data: { results, count, next: null, previous: null },
  }) as AxiosResponse<ModelsResponse>

describe('CostCalculator', () => {
  const gpt4Raw = makeRawModel()
  const claudeRaw = makeRawModel({
    id: '2',
    model_id: 'anthropic/claude-3',
    name: 'Claude 3',
    provider: 'Anthropic',
    cost_per_1m_prompt: 8,
    cost_per_1m_completion: 24,
    max_tokens: 100000,
  })
  const llamaRaw = makeRawModel({
    id: '3',
    model_id: 'meta/llama-2',
    name: 'Llama 2',
    provider: 'Meta',
    cost_per_1m_prompt: 0.1,
    cost_per_1m_completion: 0.1,
    max_tokens: 4096,
  })

  const gpt4Entry = makeEntry()
  const claudeEntry = makeEntry({
    id: '2',
    model_id: 'anthropic/claude-3',
    name: 'Claude 3',
    provider: 'Anthropic',
    cost_per_1m_prompt: 8,
    cost_per_1m_completion: 24,
    max_tokens: 100000,
  })
  const llamaEntry = makeEntry({
    id: '3',
    model_id: 'meta/llama-2',
    name: 'Llama 2',
    provider: 'Meta',
    cost_per_1m_prompt: 0.1,
    cost_per_1m_completion: 0.1,
    max_tokens: 4096,
  })

  let store: {
    comparisonModels: ModelCatalogEntry[]
    favorites: unknown[]
    addFavorite: Mock
    removeFavorite: Mock
  }

  beforeEach(() => {
    vi.clearAllMocks()
    store = {
      comparisonModels: [],
      favorites: [],
      addFavorite: vi.fn(),
      removeFavorite: vi.fn(),
    }
    mockedUseModelStore.mockImplementation(() => store)
    mockedModels.mockResolvedValue(pageResponse([gpt4Raw, claudeRaw, llamaRaw]))
  })

  const waitForModelsLoaded = async () => {
    await waitFor(() =>
      expect(screen.queryByText('Loading available models...')).not.toBeInTheDocument()
    )
  }

  /** The single visible number input when Advanced is collapsed. */
  const getRequestCountInput = () => screen.getByRole('spinbutton')

  it('shows a loading indicator while models are being fetched', async () => {
    let resolveFetch!: (value: AxiosResponse<ModelsResponse>) => void
    mockedModels.mockReturnValue(
      new Promise((resolve) => {
        resolveFetch = resolve
      }) as ReturnType<typeof llmApi.models>
    )

    render(<CostCalculator />)

    expect(screen.getByText('Loading available models...')).toBeInTheDocument()

    resolveFetch(pageResponse([gpt4Raw]))
    await waitForModelsLoaded()
  })

  it('fetches every page of available models on mount', async () => {
    mockedModels.mockImplementation(async (params) =>
      params?.page === 2
        ? pageResponse([llamaRaw], 3)
        : pageResponse([gpt4Raw, claudeRaw], 3)
    )

    render(<CostCalculator />)
    await waitForModelsLoaded()

    expect(mockedModels).toHaveBeenCalledWith({ available_only: true, page: 1 })
    expect(mockedModels).toHaveBeenCalledWith({ available_only: true, page: 2 })

    // All models from every page are selectable in the mobile sheet
    fireEvent.click(screen.getByText('Select a model...'))
    const sheetTitle = await screen.findByText('Select a model')
    const sheet = sheetTitle.closest('[role="dialog"]')!
    expect(within(sheet as HTMLElement).getByText('GPT-4')).toBeInTheDocument()
    expect(within(sheet as HTMLElement).getByText('Claude 3')).toBeInTheDocument()
    expect(within(sheet as HTMLElement).getByText('Llama 2')).toBeInTheDocument()
  })

  it('handles a fetch failure by rendering the empty state', async () => {
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {})
    mockedModels.mockRejectedValue(new Error('network down'))

    render(<CostCalculator />)
    await waitForModelsLoaded()

    expect(consoleError).toHaveBeenCalledWith('Failed to fetch models:', expect.any(Error))
    expect(screen.getByText('Select a model to see cost estimates')).toBeInTheDocument()
    consoleError.mockRestore()
  })

  it('shows the empty state until a model is selected', async () => {
    render(<CostCalculator />)
    await waitForModelsLoaded()

    expect(screen.getByText('Select a model to see cost estimates')).toBeInTheDocument()
    expect(screen.queryByText('Estimated Cost')).not.toBeInTheDocument()
    expect(screen.queryByText('Cost Breakdown')).not.toBeInTheDocument()
  })

  it('displays the estimated cost for the selected model with default usage', async () => {
    render(<CostCalculator selectedModel={gpt4Entry} />)
    await waitForModelsLoaded()

    // 1000 prompt tokens * $30/1M + 500 completion tokens * $60/1M = $0.06/request
    // 100 requests -> $6.00 total
    const bigDisplay = screen.getByText('Estimated Cost').closest('div')!
    expect(within(bigDisplay).getByText('$6.00')).toBeInTheDocument()
    expect(
      within(bigDisplay).getByText(norm(`for ${(100).toLocaleString()} API calls`))
    ).toBeInTheDocument()

    // Per request / monthly / yearly projections in the big display
    expect(within(bigDisplay).getByText('Per Request')).toBeInTheDocument()
    expect(within(bigDisplay).getByText('$0.06')).toBeInTheDocument()
    expect(within(bigDisplay).getByText(fmtCost(180))).toBeInTheDocument() // 6 * 30
    expect(within(bigDisplay).getByText(fmtCost(2190))).toBeInTheDocument() // 6 * 365
  })

  it('shows the cost breakdown split into input and output costs', async () => {
    render(<CostCalculator selectedModel={gpt4Entry} />)
    await waitForModelsLoaded()

    const breakdown = screen.getByText('Cost Breakdown').closest('div')!.parentElement!

    // Input: 1000 * $30/1M * 100 requests = $3.00; Output: 500 * $60/1M * 100 = $3.00
    expect(within(breakdown).getByText('Input Cost')).toBeInTheDocument()
    expect(within(breakdown).getByText('Output Cost')).toBeInTheDocument()
    expect(within(breakdown).getAllByText('$3.00')).toHaveLength(2)

    // Daily/weekly/monthly/yearly projections
    expect(within(breakdown).getByText('Daily')).toBeInTheDocument()
    expect(within(breakdown).getByText('$6.00')).toBeInTheDocument()
    expect(within(breakdown).getByText('Weekly')).toBeInTheDocument()
    expect(within(breakdown).getByText('$42.00')).toBeInTheDocument()
    expect(within(breakdown).getByText('Monthly')).toBeInTheDocument()
    expect(within(breakdown).getByText(fmtCost(180))).toBeInTheDocument()
    expect(within(breakdown).getByText('Yearly')).toBeInTheDocument()
    expect(within(breakdown).getByText(fmtCost(2190))).toBeInTheDocument()
  })

  it('shows pricing details for the selected model', async () => {
    render(<CostCalculator selectedModel={gpt4Entry} />)
    await waitForModelsLoaded()

    expect(screen.getAllByText('$30.00/1M').length).toBeGreaterThan(0) // input price
    expect(screen.getAllByText('$60.00/1M').length).toBeGreaterThan(0) // output price
    expect(screen.getAllByText('8K').length).toBeGreaterThan(0) // context size
    expect(screen.getAllByText('OpenAI').length).toBeGreaterThan(0) // provider badge
  })

  it('updates the estimated cost when the request count changes', async () => {
    render(<CostCalculator selectedModel={gpt4Entry} />)
    await waitForModelsLoaded()

    fireEvent.change(getRequestCountInput(), { target: { value: '1000' } })

    // $0.06/request * 1000 = $60.00
    const bigDisplay = screen.getByText('Estimated Cost').closest('div')!
    expect(within(bigDisplay).getByText('$60.00')).toBeInTheDocument()
    expect(
      within(bigDisplay).getByText(norm(`for ${(1000).toLocaleString()} API calls`))
    ).toBeInTheDocument()
  })

  it('clamps invalid request counts to a minimum of 1', async () => {
    render(<CostCalculator selectedModel={gpt4Entry} />)
    await waitForModelsLoaded()

    fireEvent.change(getRequestCountInput(), { target: { value: '-5' } })
    expect(getRequestCountInput()).toHaveValue(1)
  })

  it('sets the request count via the quick-select buttons', async () => {
    render(<CostCalculator selectedModel={gpt4Entry} />)
    await waitForModelsLoaded()

    fireEvent.click(screen.getByRole('button', { name: '1K' }))
    expect(getRequestCountInput()).toHaveValue(1000)

    fireEvent.click(screen.getByRole('button', { name: '10K' }))
    expect(getRequestCountInput()).toHaveValue(10000)
  })

  it('applies usage presets', async () => {
    render(<CostCalculator selectedModel={gpt4Entry} />)
    await waitForModelsLoaded()

    expect(screen.getByText('Presets:')).toBeInTheDocument()
    for (const preset of ['Chat Bot', 'Code Gen', 'Doc Analysis', 'Creative']) {
      expect(screen.getByRole('button', { name: preset })).toBeInTheDocument()
    }

    fireEvent.click(screen.getByRole('button', { name: 'Chat Bot' }))

    // Chat Bot preset: 500 prompt / 200 completion / 1000 requests
    // (500 * 30 + 200 * 60) / 1M = $0.027/request -> $27.00 total
    expect(getRequestCountInput()).toHaveValue(1000)
    const bigDisplay = screen.getByText('Estimated Cost').closest('div')!
    expect(within(bigDisplay).getByText('$27.00')).toBeInTheDocument()
  })

  it('reveals token inputs behind the Advanced toggle and recalculates on change', async () => {
    render(<CostCalculator selectedModel={gpt4Entry} />)
    await waitForModelsLoaded()

    expect(screen.queryByText('Input Tokens per Request')).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /Advanced/ }))

    expect(screen.getByText('Input Tokens per Request')).toBeInTheDocument()
    expect(screen.getByText('Output Tokens per Request')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Simple/ })).toBeInTheDocument()

    // Inputs default to 1000 prompt / 500 completion tokens
    const [, promptInput, completionInput] = screen.getAllByRole('spinbutton')
    expect(promptInput).toHaveValue(1000)
    expect(completionInput).toHaveValue(500)
    expect(
      screen.getByText(norm(`Approx ${(4000).toLocaleString()} characters`))
    ).toBeInTheDocument()

    fireEvent.change(promptInput, { target: { value: '2000' } })

    // (2000 * 30 + 500 * 60) / 1M = $0.09/request -> $9.00 for 100 requests
    const bigDisplay = screen.getByText('Estimated Cost').closest('div')!
    expect(within(bigDisplay).getByText('$9.00')).toBeInTheDocument()
    expect(
      screen.getByText(norm(`Approx ${(8000).toLocaleString()} characters`))
    ).toBeInTheDocument()
  })

  it('adjusts token counts via the sliders', async () => {
    render(<CostCalculator selectedModel={gpt4Entry} />)
    await waitForModelsLoaded()

    fireEvent.click(screen.getByRole('button', { name: /Advanced/ }))

    const [promptSlider] = screen.getAllByRole('slider')
    expect(promptSlider).toHaveAttribute('aria-valuenow', '1000')

    fireEvent.keyDown(promptSlider, { key: 'ArrowRight' })

    const [, promptInput] = screen.getAllByRole('spinbutton')
    expect(promptInput).toHaveValue(1100) // step is 100
  })

  it('formats very small totals as <$0.01', async () => {
    render(<CostCalculator selectedModel={llamaEntry} />)
    await waitForModelsLoaded()

    // (1000 * 0.1 + 500 * 0.1) / 1M = $0.00015/request -> $0.0015 for 10 requests
    fireEvent.click(screen.getByRole('button', { name: '10' }))

    // Both the total and the per-request figure fall under a cent
    const bigDisplay = screen.getByText('Estimated Cost').closest('div')!
    expect(within(bigDisplay).getAllByText('<$0.01').length).toBeGreaterThan(0)
  })

  it('selects a model from the mobile sheet and notifies the parent', async () => {
    const onModelSelect = vi.fn()
    render(<CostCalculator onModelSelect={onModelSelect} />)
    await waitForModelsLoaded()

    fireEvent.click(screen.getByText('Select a model...'))
    const sheetTitle = await screen.findByText('Select a model')
    const sheet = sheetTitle.closest('[role="dialog"]') as HTMLElement

    fireEvent.click(within(sheet).getByText('Claude 3'))

    expect(onModelSelect).toHaveBeenCalledWith(
      expect.objectContaining({
        model_id: 'anthropic/claude-3',
        cost_per_1m_prompt: 8,
        cost_per_1m_completion: 24,
      })
    )

    // (1000 * 8 + 500 * 24) / 1M = $0.02/request -> $2.00 for 100 requests
    const bigDisplay = screen.getByText('Estimated Cost').closest('div')!
    expect(within(bigDisplay).getByText('$2.00')).toBeInTheDocument()
  })

  it('hides the comparison section with fewer than two comparison models', async () => {
    store.comparisonModels = [gpt4Entry]
    render(<CostCalculator selectedModel={gpt4Entry} />)
    await waitForModelsLoaded()

    expect(screen.queryByText('Compare Models')).not.toBeInTheDocument()
  })

  it('compares comparison models against the selected model with savings badges', async () => {
    store.comparisonModels = [gpt4Entry, claudeEntry]
    render(<CostCalculator selectedModel={gpt4Entry} />)
    await waitForModelsLoaded()

    const comparison = screen.getByText('Compare Models').closest('div')!.parentElement!

    // GPT-4 costs $6.00, Claude 3 costs $2.00 -> Claude is 67% cheaper
    expect(within(comparison).getByText('$6.00')).toBeInTheDocument()
    expect(within(comparison).getByText('$2.00')).toBeInTheDocument()
    expect(within(comparison).getByText('-67%')).toBeInTheDocument()
  })

  it('selects a comparison model when its row is clicked', async () => {
    const onModelSelect = vi.fn()
    store.comparisonModels = [gpt4Entry, claudeEntry]
    render(<CostCalculator selectedModel={gpt4Entry} onModelSelect={onModelSelect} />)
    await waitForModelsLoaded()

    const comparison = screen.getByText('Compare Models').closest('div')!.parentElement!
    fireEvent.click(within(comparison).getByText('Claude 3'))

    expect(onModelSelect).toHaveBeenCalledWith(
      expect.objectContaining({ model_id: 'anthropic/claude-3' })
    )
    const bigDisplay = screen.getByText('Estimated Cost').closest('div')!
    expect(within(bigDisplay).getByText('$2.00')).toBeInTheDocument()
  })
})
