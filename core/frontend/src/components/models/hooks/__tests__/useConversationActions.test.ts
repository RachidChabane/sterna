import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook } from '@testing-library/react'
import { useConversationActions } from '../useConversationActions'
import { conversationsAPI } from '@/api/conversations'
import type { Chat, ChatGroup } from '../../types'

vi.mock('@/api/conversations', () => ({
  conversationsAPI: { saveToKnowledgeBase: vi.fn() },
}))

function makeChat(overrides: Partial<Chat> = {}): Chat {
  return {
    id: 'chat-1',
    model: null,
    messages: [
      { role: 'user', content: 'hi', timestamp: new Date('2026-01-01T00:00:00Z'), message_id: 'm1' },
    ],
    isLoading: false,
    parameters: {} as Chat['parameters'],
    ...overrides,
  }
}

function makeGroup(chats: Chat[], overrides: Partial<ChatGroup> = {}): ChatGroup {
  return {
    id: 'group-1',
    name: 'Group 1',
    chats,
    updatedAt: new Date('2026-01-01T00:00:00Z'),
    ...overrides,
  } as ChatGroup
}

function renderActions(overrides: Partial<Parameters<typeof useConversationActions>[0]> = {}) {
  const chats = [makeChat()]
  const base = {
    chats,
    activeGroup: makeGroup(chats),
    activeGroupId: 'group-1',
    currentModel: { model_id: 'gpt-5' } as never,
    openConsigliere: vi.fn().mockResolvedValue(null),
    setChatGroups: vi.fn(),
    toast: vi.fn(),
    setSharedInput: vi.fn(),
    setEstimatedCosts: vi.fn(),
    isSavingToKnowledgeBase: false,
    setIsSavingToKnowledgeBase: vi.fn(),
    savingChatId: null,
    setSavingChatId: vi.fn(),
    ...overrides,
  }
  return renderHook(() => useConversationActions(base))
}

describe('useConversationActions', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    Object.assign(navigator, { clipboard: { writeText: vi.fn() } })
    global.URL.createObjectURL = vi.fn(() => 'blob:mock-url')
    global.URL.revokeObjectURL = vi.fn()
  })

  it('copyConversationResponses writes the joined transcript to the clipboard and toasts', () => {
    const { result } = renderActions()
    result.current.copyConversationResponses()
    expect(navigator.clipboard.writeText).toHaveBeenCalled()
    expect(result.current).toBeDefined()
  })

  it('copyChatResponses does nothing when the chat id is not found', () => {
    const { result } = renderActions()
    result.current.copyChatResponses('missing-chat')
    expect(navigator.clipboard.writeText).not.toHaveBeenCalled()
  })

  it('copyChatResponses writes that chat only to the clipboard and toasts', () => {
    const toast = vi.fn()
    const { result } = renderActions({ toast })
    result.current.copyChatResponses('chat-1')
    expect(navigator.clipboard.writeText).toHaveBeenCalledTimes(1)
    expect(toast).toHaveBeenCalledWith(expect.objectContaining({ title: 'Copied' }))
  })

  it('exportChatResponses creates and revokes an object URL for a text blob', () => {
    const realCreateElement = document.createElement.bind(document)
    const realAnchor = realCreateElement('a')
    const clickSpy = vi.spyOn(realAnchor, 'click').mockImplementation(() => {})
    const createElementSpy = vi.spyOn(document, 'createElement').mockImplementation((tag: string) => {
      return tag === 'a' ? realAnchor : realCreateElement(tag)
    })

    const { result } = renderActions()
    result.current.exportChatResponses('chat-1')

    expect(URL.createObjectURL).toHaveBeenCalled()
    expect(clickSpy).toHaveBeenCalled()
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:mock-url')
    createElementSpy.mockRestore()
  })

  it('handleSaveChatToKnowledgeBase saves and toasts success', async () => {
    vi.mocked(conversationsAPI.saveToKnowledgeBase).mockResolvedValue({ filename: 'chat.md' } as never)
    const toast = vi.fn()
    const setSavingChatId = vi.fn()
    const { result } = renderActions({ toast, setSavingChatId })

    await result.current.handleSaveChatToKnowledgeBase('chat-1')

    expect(conversationsAPI.saveToKnowledgeBase).toHaveBeenCalledWith('group-1')
    expect(setSavingChatId).toHaveBeenCalledWith('chat-1')
    expect(setSavingChatId).toHaveBeenCalledWith(null)
    expect(toast).toHaveBeenCalledWith(expect.objectContaining({ title: 'Saved' }))
  })

  it('handleSaveChatToKnowledgeBase is a no-op while a save is already in flight', async () => {
    const { result } = renderActions({ savingChatId: 'chat-1' })
    await result.current.handleSaveChatToKnowledgeBase('chat-1')
    expect(conversationsAPI.saveToKnowledgeBase).not.toHaveBeenCalled()
  })

  it('handleSaveChatToKnowledgeBase surfaces the "already saved" toast for a duplicate save', async () => {
    vi.mocked(conversationsAPI.saveToKnowledgeBase).mockRejectedValue({
      response: { data: { existing_document_id: 'doc-1', error: 'Already there' } },
    })
    const toast = vi.fn()
    const { result } = renderActions({ toast })

    await result.current.handleSaveChatToKnowledgeBase('chat-1')

    expect(toast).toHaveBeenCalledWith(expect.objectContaining({ title: 'Already saved' }))
  })

  it('handleOpenConsigliere opens the session and records it on the active group when it changed', async () => {
    const openConsigliere = vi.fn().mockResolvedValue('session-2')
    const setChatGroups = vi.fn()
    const activeGroup = makeGroup([makeChat()], { consigliereSessionId: 'session-1' })
    const { result } = renderActions({ openConsigliere, setChatGroups, activeGroup })

    await result.current.handleOpenConsigliere()

    expect(openConsigliere).toHaveBeenCalledWith(activeGroup, 'gpt-5')
    expect(setChatGroups).toHaveBeenCalledTimes(1)
  })

  it('handleOpenConsigliere warns instead of opening when no model is selected', async () => {
    const openConsigliere = vi.fn()
    const toast = vi.fn()
    const { result } = renderActions({ openConsigliere, toast, currentModel: null })

    await result.current.handleOpenConsigliere()

    expect(openConsigliere).not.toHaveBeenCalled()
    expect(toast).toHaveBeenCalledWith(expect.objectContaining({ variant: 'destructive' }))
  })

  it('clearConversations empties every chat, resets the shared input/cost, and toasts', () => {
    const setChatGroups = vi.fn()
    const setSharedInput = vi.fn()
    const setEstimatedCosts = vi.fn()
    const { result } = renderActions({ setChatGroups, setSharedInput, setEstimatedCosts })

    result.current.clearConversations()

    const updater = setChatGroups.mock.calls[0][0]
    const updated = updater([makeGroup([makeChat()])])
    expect(updated[0].chats[0].messages).toEqual([])
    expect(updated[0].name).toBe('New Conversation')
    expect(setSharedInput).toHaveBeenCalledWith('')
    expect(setEstimatedCosts).toHaveBeenCalledWith(null)
  })
})
