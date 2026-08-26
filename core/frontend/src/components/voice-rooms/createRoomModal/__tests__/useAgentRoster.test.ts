import { describe, it, expect, vi } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useAgentRoster } from '../useAgentRoster'

vi.mock('@/store/voiceRoomStore', () => ({
  default: (selector?: (state: any) => any) => {
    const state = { recommendedVoices: [{ voice_id: 'v1', name: 'Voice One' }, { voice_id: 'v2', name: 'Voice Two' }] }
    return selector ? selector(state) : state
  },
}))

describe('useAgentRoster', () => {
  it('starts with a single default agent', () => {
    const { result } = renderHook(() => useAgentRoster())
    expect(result.current.agents).toHaveLength(1)
    expect(result.current.agents[0].order).toBe(1)
  })

  it('adds an agent up to the 6-agent cap', () => {
    const { result } = renderHook(() => useAgentRoster())

    // Each call is its own act() — handleAddAgent reads `agents` from the render
    // closure (like a real click handler firing once per render), so batching
    // several calls into one act() would silently drop all but the last.
    for (let i = 0; i < 10; i++) {
      act(() => result.current.handleAddAgent())
    }

    expect(result.current.agents).toHaveLength(6)
  })

  it('removes an agent and renumbers the remaining ones, but never below one agent', () => {
    const { result } = renderHook(() => useAgentRoster())
    act(() => result.current.handleAddAgent())
    act(() => result.current.handleAddAgent())
    expect(result.current.agents).toHaveLength(3)

    act(() => result.current.handleRemoveAgent(0))
    expect(result.current.agents).toHaveLength(2)
    expect(result.current.agents.map((a) => a.order)).toEqual([1, 2])

    act(() => result.current.handleRemoveAgent(0))
    act(() => result.current.handleRemoveAgent(0))
    // Removing the last agent is a no-op — at least one agent always remains.
    expect(result.current.agents).toHaveLength(1)
  })

  it('updates a field and, for voice_id, resolves the matching voice_name', () => {
    const { result } = renderHook(() => useAgentRoster())

    act(() => result.current.handleAgentChange(0, 'display_name', 'Host'))
    expect(result.current.agents[0].display_name).toBe('Host')

    act(() => result.current.handleAgentChange(0, 'voice_id', 'v2'))
    expect(result.current.agents[0].voice_id).toBe('v2')
    expect(result.current.agents[0].voice_name).toBe('Voice Two')
  })

  it('leaves voice_name untouched when the voice_id has no match in recommendedVoices', () => {
    const { result } = renderHook(() => useAgentRoster())
    const originalName = result.current.agents[0].voice_name

    act(() => result.current.handleAgentChange(0, 'voice_id', 'unknown-voice'))
    expect(result.current.agents[0].voice_name).toBe(originalName)
  })

  it('toggles an agent index in and out of the expanded set', () => {
    const { result } = renderHook(() => useAgentRoster())
    expect(result.current.expandedAgents.has(0)).toBe(false)

    act(() => result.current.handleToggleAgentExpand(0))
    expect(result.current.expandedAgents.has(0)).toBe(true)

    act(() => result.current.handleToggleAgentExpand(0))
    expect(result.current.expandedAgents.has(0)).toBe(false)
  })

  it('reorders agents on drag end and updates their order values', () => {
    const { result } = renderHook(() => useAgentRoster())
    act(() => result.current.handleAddAgent())
    const [firstId, secondId] = result.current.agents.map((a) => a.id)

    act(() => {
      result.current.handleDragEnd({ active: { id: firstId }, over: { id: secondId } } as any)
    })

    expect(result.current.agents.map((a) => a.id)).toEqual([secondId, firstId])
    expect(result.current.agents.map((a) => a.order)).toEqual([1, 2])
  })
})
