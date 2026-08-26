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

import { useChatPanelModelDetails } from '../useChatPanelModelDetails'
import type { Message, Model } from '../../types'

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

function makeMessage(overrides: Partial<Message> = {}): Message {
  return {
    role: 'assistant',
    content: 'hi',
    timestamp: new Date('2026-01-01T00:00:00Z'),
    ...overrides,
  } as Message
}

describe('useChatPanelModelDetails', () => {
  beforeEach(() => {
    storeState.currentModel = null
    storeState.models = []
    storeState.allModels = []
    storeState.recentModels = []
    storeState.recentChatModels = []
    storeState.favorites = []
    storeState.comparisonModels = []
  })

  it('resolveModelDetails returns null with no model id', () => {
    const { result } = renderHook(() => useChatPanelModelDetails(null, []))
    expect(result.current.resolveModelDetails()).toBeNull()
  })

  it('resolveModelDetails finds a catalog match across store lists', () => {
    const entry = { model_id: 'claude-x', name: 'Claude X (catalog)' }
    storeState.recentChatModels = [{ details: entry }]
    const { result } = renderHook(() => useChatPanelModelDetails(null, []))
    expect(result.current.resolveModelDetails('claude-x')).toBe(entry)
  })

  it('resolveModelDetails falls back to message metadata when no catalog match exists', () => {
    const messages = [makeMessage({ model_id: 'claude-x', model: 'Claude X', provider: 'anthropic' })]
    const { result } = renderHook(() => useChatPanelModelDetails(null, messages))

    const details = result.current.resolveModelDetails('claude-x')

    expect(details).toMatchObject({ model_id: 'claude-x', name: 'Claude X', provider: 'anthropic' })
  })

  it('resolveModelDetails returns null when nothing matches anywhere', () => {
    const { result } = renderHook(() => useChatPanelModelDetails(null, []))
    expect(result.current.resolveModelDetails('unknown-id')).toBeNull()
  })

  it('openModelDetails opens the panel with a resolved catalog entry', () => {
    const entry = { model_id: 'gpt-5', name: 'GPT-5 (catalog)' }
    storeState.models = [entry]
    const { result } = renderHook(() => useChatPanelModelDetails(makeModel(), []))

    act(() => { result.current.openModelDetails('gpt-5') })

    expect(result.current.isModelDetailsOpen).toBe(true)
    expect(result.current.selectedModelDetails).toBe(entry)
  })

  it('openModelDetails defaults to the current model id and falls back to a minimal entry', () => {
    const model = makeModel({ model_id: 'claude-x', name: 'Claude X' })
    const { result } = renderHook(() => useChatPanelModelDetails(model, []))

    act(() => { result.current.openModelDetails() })

    expect(result.current.isModelDetailsOpen).toBe(true)
    expect(result.current.selectedModelDetails).toMatchObject({ model_id: 'claude-x', name: 'Claude X' })
  })

  it('openModelDetails does nothing when there is no model and no resolvable id', () => {
    const { result } = renderHook(() => useChatPanelModelDetails(null, []))

    act(() => { result.current.openModelDetails() })

    expect(result.current.isModelDetailsOpen).toBe(false)
  })

  it('setIsModelDetailsOpen closes the panel', () => {
    storeState.models = [{ model_id: 'gpt-5' }]
    const { result } = renderHook(() => useChatPanelModelDetails(makeModel(), []))

    act(() => { result.current.openModelDetails() })
    expect(result.current.isModelDetailsOpen).toBe(true)

    act(() => { result.current.setIsModelDetailsOpen(false) })
    expect(result.current.isModelDetailsOpen).toBe(false)
  })

  it('keeps openModelDetails and resolveModelDetails stable across a no-op re-render, so the memoized chat context does not churn', () => {
    const model = makeModel()
    const messages: Message[] = []
    const { result, rerender } = renderHook(
      ({ model, messages }) => useChatPanelModelDetails(model, messages),
      { initialProps: { model, messages } }
    )

    const before = {
      openModelDetails: result.current.openModelDetails,
      resolveModelDetails: result.current.resolveModelDetails,
    }

    rerender({ model, messages })

    expect(result.current.openModelDetails).toBe(before.openModelDetails)
    expect(result.current.resolveModelDetails).toBe(before.resolveModelDetails)
  })
})
