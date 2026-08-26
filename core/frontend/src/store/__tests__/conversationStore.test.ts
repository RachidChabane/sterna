import { describe, it, expect, beforeEach, vi } from 'vitest'
import useConversationStore from '@/store/conversationStore'
import { conversationsAPI } from '@/api/conversations'
import type { Conversation, ConversationSummary } from '@/store/conversationStore'
import type { APIChat, APIConversation } from '@/api/conversations'
import type { Chat, Message } from '@/components/models/types'
import type { Model } from '@/api/llm'
import { getDefaultModelParameters } from '@/config/modelParameters'

// Keep the REAL converters (toFrontendConversation/toFrontendChat/toFrontendMessage) —
// only stub the network-calling methods on conversationsAPI.
vi.mock('@/api/conversations', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/conversations')>()
  return {
    ...actual,
    conversationsAPI: {
      ...actual.conversationsAPI,
      listConversationsPaginated: vi.fn(),
      getConversation: vi.fn(),
      createConversation: vi.fn(),
      updateConversation: vi.fn(),
      deleteConversation: vi.fn(),
      archiveConversation: vi.fn(),
      createChat: vi.fn(),
      updateChat: vi.fn(),
      deleteChat: vi.fn(),
      createMessage: vi.fn(),
      createMessagesBulk: vi.fn(),
      updateMessage: vi.fn(),
      deleteMessage: vi.fn(),
    },
  }
})

function makeChat(overrides: Partial<Chat> = {}): Chat {
  return {
    id: 'chat-1',
    model: null,
    messages: [],
    isLoading: false,
    parameters: getDefaultModelParameters(),
    ...overrides,
  } as Chat
}

function makeConversation(overrides: Partial<Conversation> = {}): Conversation {
  return {
    id: 'conv-1',
    name: 'Test conversation',
    createdAt: new Date('2026-01-01'),
    updatedAt: new Date('2026-01-01'),
    chats: [makeChat()],
    ...overrides,
  }
}

function makeModel(overrides: Partial<Model> = {}): Model {
  return {
    id: 'model-1',
    model_id: 'openai/gpt-4o',
    name: 'GPT-4o',
    provider: 'openai',
    cost_per_1m_prompt: 1,
    cost_per_1m_completion: 2,
    max_tokens: 128000,
    supports_streaming: true,
    supports_functions: true,
    supports_structured_outputs: true,
    supports_reasoning: false,
    supports_prompt_caching: true,
    supports_stream_cancellation: true,
    input_modalities: ['text'],
    is_available: true,
    ...overrides,
  }
}

function makeApiChat(overrides: Partial<APIChat> = {}): APIChat {
  return {
    id: 'chat-2',
    model_id: 'openai/gpt-4o',
    model_provider: 'openai',
    parameters: getDefaultModelParameters(),
    position: 0,
    is_disabled: false,
    is_hidden: false,
    message_count: 0,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    ...overrides,
  }
}

function makeApiConversation(overrides: Partial<APIConversation> = {}): APIConversation {
  return {
    id: 'conv-1',
    user: 'u1',
    name: 'Test conversation',
    is_custom_name: false,
    is_archived: false,
    is_pinned: false,
    consigliere_session_id: null,
    message_count: 0,
    chat_count: 1,
    model_id: null,
    model_provider: null,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    last_message_at: null,
    ...overrides,
  }
}

function makeConversationSummary(overrides: Partial<ConversationSummary> = {}): ConversationSummary {
  return {
    id: 'conv-1',
    name: 'Test conversation',
    isCustomName: false,
    isArchived: false,
    isPinned: false,
    messageCount: 0,
    chatCount: 1,
    modelId: null,
    modelProvider: null,
    chatModels: [],
    createdAt: new Date('2026-01-01'),
    updatedAt: new Date('2026-01-01'),
    lastMessageAt: null,
    ...overrides,
  }
}

describe('conversationStore', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useConversationStore.setState({
      conversations: [],
      activeConversation: null,
      activeConversationId: null,
      totalCount: 0,
      currentPage: 1,
      hasMore: false,
      isLoading: false,
      isLoadingMore: false,
      isLoadingConversation: false,
      isSaving: false,
      error: null,
      generatingTitleForId: null,
      generatingTitleText: '',
    })
  })

  describe('fetchConversations', () => {
    it('loads and normalizes the paginated conversation list', async () => {
      vi.mocked(conversationsAPI.listConversationsPaginated).mockResolvedValue({
        count: 1,
        next: null,
        previous: null,
        results: [
          {
            id: 'conv-1',
            user: 'u1',
            name: 'Hello',
            is_custom_name: false,
            is_archived: false,
            is_pinned: false,
            consigliere_session_id: null,
            message_count: 0,
            chat_count: 1,
            model_id: 'openai/gpt-4o',
            model_provider: 'openai',
            created_at: '2026-01-01T00:00:00Z',
            updated_at: '2026-01-01T00:00:00Z',
            last_message_at: null,
          },
        ],
      })

      await useConversationStore.getState().fetchConversations()

      const state = useConversationStore.getState()
      expect(state.conversations).toHaveLength(1)
      expect(state.conversations[0].name).toBe('Hello')
      expect(state.hasMore).toBe(false)
      expect(state.isLoading).toBe(false)
    })

    it('sets an error and stops loading when the request fails', async () => {
      vi.mocked(conversationsAPI.listConversationsPaginated).mockRejectedValue(new Error('network'))

      await useConversationStore.getState().fetchConversations()

      const state = useConversationStore.getState()
      expect(state.error).toBe('Failed to load conversations')
      expect(state.isLoading).toBe(false)
    })
  })

  describe('addMessage', () => {
    it('appends a message to the matching chat when the conversation is active', async () => {
      useConversationStore.setState({
        activeConversation: makeConversation(),
        activeConversationId: 'conv-1',
      })
      vi.mocked(conversationsAPI.createMessage).mockResolvedValue({
        id: 'msg-1',
        chat: 'chat-1',
        role: 'user',
        content: { text: 'hi' },
        sequence: 0,
        model_id: null,
        model_provider: null,
        prompt_tokens: null,
        completion_tokens: null,
        cost: null,
        tool_calls: [],
        tool_call_id: null,
        steps: [],
        metadata: {},
        is_stopped: false,
        sparks: [],
        created_at: '2026-01-01T00:00:00Z',
      })

      const result = await useConversationStore.getState().addMessage('conv-1', 'chat-1', {
        role: 'user',
        content: 'hi',
      })

      expect(result.content).toBe('hi')
      const chat = useConversationStore.getState().activeConversation!.chats[0]
      expect(chat.messages).toHaveLength(1)
      expect(chat.messages[0].message_id).toBe('msg-1')
    })

    it('does NOT mutate state when the conversationId does not match the active conversation (silent no-op)', async () => {
      useConversationStore.setState({
        activeConversation: makeConversation(),
        activeConversationId: 'conv-1',
      })
      vi.mocked(conversationsAPI.createMessage).mockResolvedValue({
        id: 'msg-1',
        chat: 'chat-1',
        role: 'user',
        content: { text: 'hi' },
        sequence: 0,
        model_id: null,
        model_provider: null,
        prompt_tokens: null,
        completion_tokens: null,
        cost: null,
        tool_calls: [],
        tool_call_id: null,
        steps: [],
        metadata: {},
        is_stopped: false,
        sparks: [],
        created_at: '2026-01-01T00:00:00Z',
      })

      // Call with a DIFFERENT conversationId than the active one.
      const result = await useConversationStore.getState().addMessage('conv-OTHER', 'chat-1', {
        role: 'user',
        content: 'hi',
      })

      // The API call still happens and returns a message...
      expect(result.content).toBe('hi')
      // ...but the active conversation's chats are untouched.
      expect(useConversationStore.getState().activeConversation!.chats[0].messages).toHaveLength(0)
    })
  })

  describe('addChat', () => {
    it('adds a new chat to the active conversation with the given model', async () => {
      useConversationStore.setState({
        activeConversation: makeConversation({ chats: [] }),
        activeConversationId: 'conv-1',
      })
      vi.mocked(conversationsAPI.createChat).mockResolvedValue(makeApiChat())

      const model = makeModel({ model_id: 'openai/gpt-4o', provider: 'openai', name: 'GPT-4o' })
      const chat = await useConversationStore.getState().addChat('conv-1', model)

      expect(chat.id).toBe('chat-2')
      expect(useConversationStore.getState().activeConversation!.chats).toHaveLength(1)
    })
  })

  describe('updateChat — per-chat model override vs app-level model', () => {
    it('updates a chat model independently of other chats in the same conversation', async () => {
      const chatA = makeChat({ id: 'chat-a', model: makeModel({ model_id: 'openai/gpt-4o' }) })
      const chatB = makeChat({ id: 'chat-b', model: makeModel({ model_id: 'anthropic/claude' }) })
      useConversationStore.setState({
        activeConversation: makeConversation({ chats: [chatA, chatB] }),
        activeConversationId: 'conv-1',
      })
      vi.mocked(conversationsAPI.updateChat).mockResolvedValue(makeApiChat())

      const newModel = makeModel({ model_id: 'google/gemini', provider: 'google' })
      await useConversationStore.getState().updateChat('conv-1', 'chat-a', { model: newModel })

      const chats = useConversationStore.getState().activeConversation!.chats
      expect(chats.find(c => c.id === 'chat-a')!.model!.model_id).toBe('google/gemini')
      // chat-b untouched — proves per-chat model is independent
      expect(chats.find(c => c.id === 'chat-b')!.model!.model_id).toBe('anthropic/claude')
    })
  })

  describe('removeChat', () => {
    it('removes the chat from the active conversation', async () => {
      const chatA = makeChat({ id: 'chat-a' })
      const chatB = makeChat({ id: 'chat-b' })
      useConversationStore.setState({
        activeConversation: makeConversation({ chats: [chatA, chatB] }),
        activeConversationId: 'conv-1',
      })
      vi.mocked(conversationsAPI.deleteChat).mockResolvedValue(undefined)

      await useConversationStore.getState().removeChat('conv-1', 'chat-a')

      const chats = useConversationStore.getState().activeConversation!.chats
      expect(chats.map(c => c.id)).toEqual(['chat-b'])
    })
  })

  describe('local optimistic updates', () => {
    it('appendLocalMessage adds a message without calling the API', () => {
      useConversationStore.setState({
        activeConversation: makeConversation(),
        activeConversationId: 'conv-1',
      })
      const message: Message = { role: 'assistant', content: 'streaming...', timestamp: new Date() }

      useConversationStore.getState().appendLocalMessage('chat-1', message)

      expect(conversationsAPI.createMessage).not.toHaveBeenCalled()
      expect(useConversationStore.getState().activeConversation!.chats[0].messages).toHaveLength(1)
    })

    it('updateLocalMessage merges partial data into the matching message by message_id', () => {
      const existing: Message = { role: 'assistant', content: 'partial', timestamp: new Date(), message_id: 'm1' }
      useConversationStore.setState({
        activeConversation: makeConversation({ chats: [makeChat({ messages: [existing] })] }),
        activeConversationId: 'conv-1',
      })

      useConversationStore.getState().updateLocalMessage('chat-1', 'm1', { content: 'final' })

      expect(useConversationStore.getState().activeConversation!.chats[0].messages[0].content).toBe('final')
    })

    it('appendLocalMessage works even when the conversationId is not the active one (matches by chatId only)', () => {
      useConversationStore.setState({
        activeConversation: makeConversation(),
        activeConversationId: 'SOME-OTHER-CONVERSATION',
      })
      const message: Message = { role: 'assistant', content: 'x', timestamp: new Date() }

      useConversationStore.getState().appendLocalMessage('chat-1', message)

      // No conversationId check on this action — always applies by chatId.
      expect(useConversationStore.getState().activeConversation!.chats[0].messages).toHaveLength(1)
    })

    it('setChatLoading toggles the isLoading flag for the matching chat only', () => {
      const chatA = makeChat({ id: 'chat-a', isLoading: false })
      const chatB = makeChat({ id: 'chat-b', isLoading: false })
      useConversationStore.setState({
        activeConversation: makeConversation({ chats: [chatA, chatB] }),
        activeConversationId: 'conv-1',
      })

      useConversationStore.getState().setChatLoading('chat-a', true)

      const chats = useConversationStore.getState().activeConversation!.chats
      expect(chats.find(c => c.id === 'chat-a')!.isLoading).toBe(true)
      expect(chats.find(c => c.id === 'chat-b')!.isLoading).toBe(false)
    })
  })

  describe('title generation', () => {
    it('startGeneratingTitle sets the placeholder name in the conversation list', () => {
      useConversationStore.setState({
        conversations: [makeConversationSummary({ name: 'Old name' })],
      })

      useConversationStore.getState().startGeneratingTitle('conv-1', 'New Conversation')

      const state = useConversationStore.getState()
      expect(state.generatingTitleForId).toBe('conv-1')
      expect(state.conversations[0].name).toBe('New Conversation')
    })

    it('finishGeneratingTitle persists the final title via updateConversation and clears streaming state', async () => {
      useConversationStore.setState({
        generatingTitleForId: 'conv-1',
        generatingTitleText: 'Draft',
        conversations: [makeConversationSummary({ name: 'Draft' })],
      })
      vi.mocked(conversationsAPI.updateConversation).mockResolvedValue(makeApiConversation())

      await useConversationStore.getState().finishGeneratingTitle('Final Title')

      expect(conversationsAPI.updateConversation).toHaveBeenCalledWith('conv-1', expect.objectContaining({
        name: 'Final Title',
        is_custom_name: false,
      }))
      const state = useConversationStore.getState()
      expect(state.generatingTitleForId).toBeNull()
      expect(state.conversations[0].name).toBe('Final Title')
    })
  })

  describe('getActiveChat', () => {
    it('returns the first chat of the active conversation', () => {
      const chat = makeChat({ id: 'first' })
      useConversationStore.setState({ activeConversation: makeConversation({ chats: [chat] }) })
      expect(useConversationStore.getState().getActiveChat()?.id).toBe('first')
    })

    it('returns null when there is no active conversation', () => {
      useConversationStore.setState({ activeConversation: null })
      expect(useConversationStore.getState().getActiveChat()).toBeNull()
    })
  })
})
