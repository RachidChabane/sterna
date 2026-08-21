import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { useActiveConversationStore } from '@/store/activeConversationStore'

describe('activeConversationStore', () => {
  beforeEach(() => {
    useActiveConversationStore.setState({
      activeConversationId: null,
      generatingTitleForId: null,
      generatingTitleText: '',
      newConversation: null,
      refreshTrigger: 0,
    })
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('setActiveConversationId updates the id', () => {
    useActiveConversationStore.getState().setActiveConversationId('conv-1')
    expect(useActiveConversationStore.getState().activeConversationId).toBe('conv-1')
  })

  it('triggerRefresh increments refreshTrigger each call', () => {
    useActiveConversationStore.getState().triggerRefresh()
    useActiveConversationStore.getState().triggerRefresh()
    expect(useActiveConversationStore.getState().refreshTrigger).toBe(2)
  })

  it('startGeneratingTitle seeds newConversation with the initial name', () => {
    useActiveConversationStore.getState().startGeneratingTitle('conv-1', 'New Conversation')

    const state = useActiveConversationStore.getState()
    expect(state.generatingTitleForId).toBe('conv-1')
    expect(state.newConversation).toEqual({ id: 'conv-1', name: 'New Conversation' })
  })

  it('updateGeneratingTitle streams text into both generatingTitleText and newConversation.name', () => {
    useActiveConversationStore.getState().startGeneratingTitle('conv-1')
    useActiveConversationStore.getState().updateGeneratingTitle('Partial ti')

    const state = useActiveConversationStore.getState()
    expect(state.generatingTitleText).toBe('Partial ti')
    expect(state.newConversation?.name).toBe('Partial ti')
  })

  it('finishGeneratingTitle with a final title clears the streaming fields but keeps newConversation for a grace period', () => {
    vi.useFakeTimers()
    useActiveConversationStore.getState().startGeneratingTitle('conv-1')

    useActiveConversationStore.getState().finishGeneratingTitle('Final Title')

    let state = useActiveConversationStore.getState()
    expect(state.generatingTitleForId).toBeNull()
    expect(state.generatingTitleText).toBe('')
    expect(state.newConversation).toEqual({ id: 'conv-1', name: 'Final Title' })

    // newConversation is cleared only after the 60s grace period.
    vi.advanceTimersByTime(60000)
    state = useActiveConversationStore.getState()
    expect(state.newConversation).toBeNull()
  })

  it('finishGeneratingTitle with no final title clears everything immediately', () => {
    useActiveConversationStore.getState().startGeneratingTitle('conv-1')

    useActiveConversationStore.getState().finishGeneratingTitle()

    const state = useActiveConversationStore.getState()
    expect(state.generatingTitleForId).toBeNull()
    expect(state.newConversation).toBeNull()
  })
})
