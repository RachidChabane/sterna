import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'

const storeState = {
  currentModel: null as unknown,
  models: [] as unknown[],
  allModels: [] as unknown[],
  recentModels: [] as { details?: unknown }[],
  recentChatModels: [] as { details?: unknown }[],
  favorites: [] as { details?: unknown }[],
  comparisonModels: [] as unknown[],
}

vi.mock('@/store/modelStore', () => ({
  default: () => storeState,
}))

import { useModelDetailsPanel } from '../useModelDetailsPanel'
import type { Model } from '../../types'

function makeModel(overrides: Partial<Model> = {}): Model {
  return {
    id: 'model-uuid-1',
    model_id: 'gpt-5',
    name: 'GPT-5',
    provider: 'openai',
    cost_per_1m_prompt: 5,
    cost_per_1m_completion: 15,
    max_tokens: 128000,
    supports_streaming: true,
    supports_functions: true,
    supports_structured_outputs: true,
    supports_reasoning: false,
    supports_prompt_caching: false,
    supports_stream_cancellation: true,
    input_modalities: ['text'],
    is_available: true,
    ...overrides,
  } as Model
}

describe('useModelDetailsPanel', () => {
  beforeEach(() => {
    storeState.currentModel = null
    storeState.models = []
    storeState.allModels = []
    storeState.recentModels = []
    storeState.recentChatModels = []
    storeState.favorites = []
    storeState.comparisonModels = []
  })

  it('does nothing when no model id can be resolved', () => {
    const { result } = renderHook(() => useModelDetailsPanel(null))

    act(() => {
      result.current.handleOpenModelDetails()
    })

    expect(result.current.isModelDetailsOpen).toBe(false)
    expect(result.current.selectedModelDetails).toBeNull()
  })

  it('finds a matching entry in the model store and opens the panel with it', () => {
    const entry = { model_id: 'gpt-5', name: 'GPT-5 (catalog)' }
    storeState.allModels = [entry]

    const { result } = renderHook(() => useModelDetailsPanel(makeModel()))

    act(() => {
      result.current.handleOpenModelDetails('gpt-5')
    })

    expect(result.current.isModelDetailsOpen).toBe(true)
    expect(result.current.selectedModelDetails).toBe(entry)
  })

  it('falls back to a minimal entry built from the chat model when no catalog match exists', () => {
    const model = makeModel({ model_id: 'claude-x', name: 'Claude X' })
    const { result } = renderHook(() => useModelDetailsPanel(model))

    act(() => {
      result.current.handleOpenModelDetails('claude-x')
    })

    expect(result.current.isModelDetailsOpen).toBe(true)
    expect(result.current.selectedModelDetails).toMatchObject({
      model_id: 'claude-x',
      name: 'Claude X',
      provider: 'openai',
    })
  })

  it('defaults the target model id to the current chat model when none is passed', () => {
    const entry = { model_id: 'gpt-5', name: 'GPT-5 (catalog)' }
    storeState.models = [entry]

    const { result } = renderHook(() => useModelDetailsPanel(makeModel({ model_id: 'gpt-5' })))

    act(() => {
      result.current.handleOpenModelDetails()
    })

    expect(result.current.selectedModelDetails).toBe(entry)
  })

  it('setIsModelDetailsOpen closes the panel', () => {
    storeState.models = [{ model_id: 'gpt-5' }]
    const { result } = renderHook(() => useModelDetailsPanel(makeModel({ model_id: 'gpt-5' })))

    act(() => {
      result.current.handleOpenModelDetails()
    })
    expect(result.current.isModelDetailsOpen).toBe(true)

    act(() => {
      result.current.setIsModelDetailsOpen(false)
    })
    expect(result.current.isModelDetailsOpen).toBe(false)
  })
})
