import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import {
  vi,
  describe,
  it,
  expect,
  beforeEach,
  beforeAll,
  type Mock,
} from 'vitest'
import { ModelFilters } from '../ModelFilters'
import useModelStore from '@/store/modelStore'
import type { ModelFilter } from '@/types/models'

// The component reads { filter, setFilter, clearFilter, fetchModels } via a
// whole-store call, so mock the default export as a fn returning an object.
vi.mock('@/store/modelStore', () => ({
  default: vi.fn(),
}))

// Providers come from the shared stats hook (backed by an API singleton);
// mock at that boundary to avoid network access.
vi.mock('@/hooks/useModelStats', () => ({
  useModelStats: () => ({
    stats: { total: 3, providers: 3, providersList: ['Anthropic', 'Meta', 'OpenAI'] },
    loading: false,
  }),
  invalidateModelStatsCache: vi.fn(),
}))

const mockedUseModelStore = useModelStore as unknown as Mock

describe('ModelFilters (desktop layout)', () => {
  // setup.ts mocks matchMedia with matches: false, so useMediaQuery reports
  // desktop and the inline filter bar renders.

  let store: {
    filter: ModelFilter
    setFilter: Mock
    clearFilter: Mock
    fetchModels: Mock
  }

  beforeAll(() => {
    // Radix Select needs these DOM APIs, which jsdom does not implement.
    window.HTMLElement.prototype.scrollIntoView = vi.fn()
    window.HTMLElement.prototype.hasPointerCapture = vi.fn().mockReturnValue(false)
    window.HTMLElement.prototype.releasePointerCapture = vi.fn()
  })

  beforeEach(() => {
    vi.clearAllMocks()
    store = {
      filter: {},
      setFilter: vi.fn(),
      clearFilter: vi.fn(),
      fetchModels: vi.fn(),
    }
    mockedUseModelStore.mockImplementation(() => store)
  })

  const user = () => userEvent.setup({ pointerEventsCheck: 0 })

  /** The "more filters" popover trigger is the icon-only button holding the sliders icon. */
  const getMoreFiltersTrigger = () => {
    const trigger = screen
      .getAllByRole('button')
      .find((b) => b.querySelector('svg.lucide-sliders-horizontal'))
    expect(trigger).toBeDefined()
    return trigger!
  }
  const openMoreFilters = () => {
    fireEvent.click(getMoreFiltersTrigger())
  }

  describe('search', () => {
    it('renders the search input', () => {
      render(<ModelFilters />)
      expect(screen.getByPlaceholderText('Search...')).toBeInTheDocument()
    })

    it('initializes the search input from the store filter', () => {
      store.filter = { search: 'claude' }
      render(<ModelFilters />)
      expect(screen.getByPlaceholderText('Search...')).toHaveValue('claude')
    })

    it('debounces search: updates filter and refetches after typing', async () => {
      const onFilterChange = vi.fn()
      render(<ModelFilters onFilterChange={onFilterChange} />)

      fireEvent.change(screen.getByPlaceholderText('Search...'), {
        target: { value: 'GPT' },
      })

      // Not applied synchronously (300ms debounce)
      expect(store.setFilter).not.toHaveBeenCalled()

      await waitFor(
        () => expect(store.setFilter).toHaveBeenCalledWith({ search: 'GPT' }),
        { timeout: 1000 }
      )
      expect(store.fetchModels).toHaveBeenCalledWith(1, { search: 'GPT' })
      expect(onFilterChange).toHaveBeenCalledWith({ search: 'GPT' })
    })

    it('clears the search via the inline X button', async () => {
      render(<ModelFilters />)

      const input = screen.getByPlaceholderText('Search...')
      fireEvent.change(input, { target: { value: 'GPT' } })
      await waitFor(() =>
        expect(store.setFilter).toHaveBeenCalledWith({ search: 'GPT' })
      )

      const clearButton = input.parentElement!.querySelector('button')
      expect(clearButton).not.toBeNull()
      fireEvent.click(clearButton!)

      expect(input).toHaveValue('')
      await waitFor(() =>
        expect(store.setFilter).toHaveBeenCalledWith({ search: undefined })
      )
    })
  })

  describe('provider select', () => {
    it('lists all providers from the stats hook', async () => {
      render(<ModelFilters />)

      await user().click(screen.getByRole('combobox'))

      expect(await screen.findByRole('option', { name: 'All providers' })).toBeInTheDocument()
      expect(screen.getByRole('option', { name: 'OpenAI' })).toBeInTheDocument()
      expect(screen.getByRole('option', { name: 'Anthropic' })).toBeInTheDocument()
      expect(screen.getByRole('option', { name: 'Meta' })).toBeInTheDocument()
    })

    it('applies a provider filter and refetches page 1', async () => {
      const onFilterChange = vi.fn()
      const onApply = vi.fn()
      render(<ModelFilters onFilterChange={onFilterChange} onApply={onApply} />)

      const u = user()
      await u.click(screen.getByRole('combobox'))
      await u.click(await screen.findByRole('option', { name: 'OpenAI' }))

      expect(store.setFilter).toHaveBeenCalledWith({ provider: 'OpenAI' })
      expect(store.fetchModels).toHaveBeenCalledWith(1, { provider: 'OpenAI' })
      expect(onFilterChange).toHaveBeenCalledWith({ provider: 'OpenAI' })
      expect(onApply).toHaveBeenCalled()
    })

    it('clears the provider when selecting All providers', async () => {
      store.filter = { provider: 'OpenAI' }
      render(<ModelFilters />)

      const u = user()
      await u.click(screen.getByRole('combobox'))
      await u.click(await screen.findByRole('option', { name: 'All providers' }))

      expect(store.setFilter).toHaveBeenCalledWith({ provider: undefined })
    })
  })

  describe('sorting', () => {
    it('does not render the sort select without an onSortByChange handler', () => {
      render(<ModelFilters />)
      // Only the provider select is a combobox
      expect(screen.getAllByRole('combobox')).toHaveLength(1)
    })

    it('notifies the parent when a sort option is chosen', async () => {
      const onSortByChange = vi.fn()
      render(<ModelFilters sortBy="none" onSortByChange={onSortByChange} />)

      const u = user()
      const [, sortTrigger] = screen.getAllByRole('combobox')
      await u.click(sortTrigger)
      await u.click(await screen.findByRole('option', { name: 'Prompt cost' }))

      expect(onSortByChange).toHaveBeenCalledWith('prompt_cost')
    })

    it('offers all current sort options', async () => {
      render(<ModelFilters sortBy="none" onSortByChange={vi.fn()} />)

      const [, sortTrigger] = screen.getAllByRole('combobox')
      await user().click(sortTrigger)
      await screen.findByRole('option', { name: 'Default' })

      for (const label of [
        'Prompt cost',
        'Completion cost',
        'Overall cost',
        'Context size',
        'Latency',
        'Throughput',
      ]) {
        expect(screen.getByRole('option', { name: label })).toBeInTheDocument()
      }
    })

    it('toggles sort order via the arrow button inside the sort trigger', () => {
      const onSortOrderChange = vi.fn()
      render(
        <ModelFilters
          sortBy="prompt_cost"
          sortOrder="asc"
          onSortByChange={vi.fn()}
          onSortOrderChange={onSortOrderChange}
        />
      )

      const arrowIcon = document.querySelector('svg.lucide-arrow-up')
      expect(arrowIcon).not.toBeNull()
      fireEvent.click(arrowIcon!.closest('button')!)

      expect(onSortOrderChange).toHaveBeenCalledWith('desc')
    })

    it('shows a descending arrow when sortOrder is desc', () => {
      render(
        <ModelFilters
          sortBy="prompt_cost"
          sortOrder="desc"
          onSortByChange={vi.fn()}
          onSortOrderChange={vi.fn()}
        />
      )

      expect(document.querySelector('svg.lucide-arrow-down')).not.toBeNull()
      expect(document.querySelector('svg.lucide-arrow-up')).toBeNull()
    })
  })

  describe('more-filters popover', () => {
    it('opens with context window, capabilities, input types and price sections', async () => {
      render(<ModelFilters />)

      openMoreFilters()

      expect(await screen.findByText('Context window')).toBeInTheDocument()
      expect(screen.getByText('Capabilities')).toBeInTheDocument()
      expect(screen.getByText('Input types')).toBeInTheDocument()
      expect(screen.getByText('Max price')).toBeInTheDocument()
      // Price slider shows "Any price" when no max price is set
      expect(screen.getByText('Any price')).toBeInTheDocument()
    })

    it('applies a minimum context length filter', async () => {
      render(<ModelFilters />)

      openMoreFilters()
      fireEvent.click(await screen.findByText('200K+'))

      expect(store.setFilter).toHaveBeenCalledWith({ minContextLength: 200000 })
      expect(store.fetchModels).toHaveBeenCalledWith(1, { minContextLength: 200000 })
    })

    it('toggles a capability on', async () => {
      const onFilterChange = vi.fn()
      render(<ModelFilters onFilterChange={onFilterChange} />)

      openMoreFilters()
      fireEvent.click(await screen.findByText('Reasoning'))

      expect(store.setFilter).toHaveBeenCalledWith({
        capabilities: { reasoning: true },
      })
      expect(onFilterChange).toHaveBeenCalledWith(
        expect.objectContaining({ capabilities: { reasoning: true } })
      )
    })

    it('toggles an active capability off and drops the empty capabilities object', async () => {
      store.filter = { capabilities: { reasoning: true } }
      render(<ModelFilters />)

      openMoreFilters()
      fireEvent.click(await screen.findByText('Reasoning'))

      expect(store.setFilter).toHaveBeenCalledWith(
        expect.objectContaining({ capabilities: undefined })
      )
    })

    it('toggles input modalities (Vision -> image)', async () => {
      render(<ModelFilters />)

      openMoreFilters()
      fireEvent.click(await screen.findByText('Vision'))

      expect(store.setFilter).toHaveBeenCalledWith({ input_modalities: ['image'] })
    })

    it('removes a selected modality when toggled again', async () => {
      store.filter = { input_modalities: ['image'] }
      render(<ModelFilters />)

      openMoreFilters()
      fireEvent.click(await screen.findByText('Vision'))

      expect(store.setFilter).toHaveBeenCalledWith(
        expect.objectContaining({ input_modalities: undefined })
      )
    })

    it('resets filters from the popover Reset button', async () => {
      store.filter = { provider: 'OpenAI', minContextLength: 131072 }
      render(<ModelFilters />)

      openMoreFilters()

      fireEvent.click(await screen.findByText('Reset'))

      expect(store.clearFilter).toHaveBeenCalled()
      expect(store.fetchModels).toHaveBeenCalledWith(1, {})
    })
  })

  describe('active filter indicators', () => {
    it('shows the active filter count on the popover trigger', () => {
      store.filter = { provider: 'OpenAI', minContextLength: 131072 }
      render(<ModelFilters />)

      expect(getMoreFiltersTrigger()).toHaveTextContent('2')
    })

    it('counts each selected input modality', () => {
      store.filter = { input_modalities: ['image', 'audio'] }
      render(<ModelFilters />)

      expect(getMoreFiltersTrigger()).toHaveTextContent('2')
    })

    it('shows a clear-all button when filters are active and clears everything', () => {
      const onFilterChange = vi.fn()
      store.filter = { provider: 'OpenAI' }
      render(<ModelFilters onFilterChange={onFilterChange} />)

      const clearAll = screen.getByTitle('Clear filters')
      fireEvent.click(clearAll)

      expect(store.clearFilter).toHaveBeenCalled()
      expect(store.fetchModels).toHaveBeenCalledWith(1, {})
      expect(onFilterChange).toHaveBeenCalledWith({})
    })

    it('hides the clear-all button when no filters are active', () => {
      render(<ModelFilters />)
      expect(screen.queryByTitle('Clear filters')).not.toBeInTheDocument()
    })
  })
})
