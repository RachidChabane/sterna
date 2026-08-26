import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook } from '@testing-library/react'

const getActiveServers = vi.fn()

vi.mock('@/store/mcpStore', () => ({
  useMCPStore: (selector: (state: { getActiveServers: () => unknown[] }) => unknown) =>
    selector({ getActiveServers }),
}))

import { useChatFeatureToggles } from '../useChatFeatureToggles'
import type { Model, ModelParameters } from '../../types'

function makeModel(overrides: Partial<Model> = {}): Model {
  return {
    id: 'model-1',
    model_id: 'gpt-5',
    name: 'GPT-5',
    provider: 'openai',
    cost_per_1m_prompt: 5,
    cost_per_1m_completion: 15,
    max_tokens: 128000,
    supports_streaming: true,
    supports_functions: true,
    supports_structured_outputs: true,
    supports_reasoning: true,
    supports_prompt_caching: false,
    supports_stream_cancellation: true,
    input_modalities: ['text'],
    is_available: true,
    ...overrides,
  } as Model
}

describe('useChatFeatureToggles', () => {
  beforeEach(() => {
    getActiveServers.mockReset()
    getActiveServers.mockReturnValue(['server-a'])
  })

  it('reports support flags from the current model', () => {
    const { result } = renderHook(() => useChatFeatureToggles({ model: makeModel(), parameters: {} }))
    expect(result.current.hasWebSearchSupportValue).toBe(true)
    expect(result.current.hasReasoningSupportValue).toBe(true)
    expect(result.current.hasFunctionSupportValue).toBe(true)
  })

  it('reports unsupported when the model lacks the capability', () => {
    const model = makeModel({ supports_functions: false, supports_reasoning: false })
    const { result } = renderHook(() => useChatFeatureToggles({ model, parameters: {} }))
    expect(result.current.webSearchState.supported).toBe(0)
    expect(result.current.reasoningState.supported).toBe(0)
    expect(result.current.mcpToolsState.supported).toBe(0)
  })

  it('reflects the enabled flag from parameters', () => {
    const parameters: ModelParameters = { enable_brave_search: true, enable_reasoning: false, enable_mcp_tools: true }
    const { result } = renderHook(() => useChatFeatureToggles({ model: makeModel(), parameters }))
    expect(result.current.webSearchState.enabled).toBe(1)
    expect(result.current.reasoningState.enabled).toBe(0)
    expect(result.current.mcpToolsState.enabled).toBe(1)
  })

  it('toggleWebSearch flips enable_brave_search via onParametersChange', () => {
    const onParametersChange = vi.fn()
    const parameters: ModelParameters = { enable_brave_search: false }
    const { result } = renderHook(() => useChatFeatureToggles({ model: makeModel(), parameters, onParametersChange }))

    result.current.toggleWebSearch()

    expect(onParametersChange).toHaveBeenCalledWith({ enable_brave_search: true })
  })

  it('toggleReasoning and toggleMCPTools are no-ops without a change handler or parameters', () => {
    const onParametersChange = vi.fn()
    const { result } = renderHook(() => useChatFeatureToggles({ model: makeModel(), parameters: undefined, onParametersChange }))

    result.current.toggleReasoning()
    result.current.toggleMCPTools()

    expect(onParametersChange).not.toHaveBeenCalled()
  })

  it('surfaces the active MCP servers from the store', () => {
    const { result } = renderHook(() => useChatFeatureToggles({ model: makeModel(), parameters: {} }))
    expect(result.current.activeServersValue).toEqual(['server-a'])
  })

  it('falls back to an empty list when getActiveServers throws', () => {
    getActiveServers.mockImplementation(() => { throw new Error('boom') })
    const { result } = renderHook(() => useChatFeatureToggles({ model: makeModel(), parameters: {} }))
    expect(result.current.activeServersValue).toEqual([])
  })
})
