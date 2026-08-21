import { describe, it, expect, beforeEach, vi } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useMessageSending } from '@/hooks/useMessageSending'
import { llmApi } from '@/api/llm'
import { conversationsAPI } from '@/api/conversations'
import { useUsageQuotaStore } from '@/store/usageQuotaStore'
import type { Chat, Message, Model } from '@/components/models/types'
import { getDefaultModelParameters } from '@/config/modelParameters'

vi.mock('@/api/llm', () => ({
  llmApi: {
    completeStream: vi.fn(),
    getGenerationUsage: vi.fn().mockResolvedValue({ usage: { prompt_tokens: 0, completion_tokens: 0 }, cost: 0 }),
  },
}))

vi.mock('@/api/conversations', () => ({
  conversationsAPI: {
    createMessage: vi.fn().mockResolvedValue({ id: 'persisted-msg-1' }),
    updateMessage: vi.fn().mockResolvedValue({}),
  },
}))

vi.mock('@/api/sparks', () => ({
  sparksAPI: { createBatch: vi.fn().mockResolvedValue([]) },
}))

vi.mock('@/api/codeSession', () => ({
  codeSessionApi: {
    sendCodingAgentAnswer: vi.fn().mockResolvedValue({}),
    getPlan: vi.fn().mockResolvedValue({ data: {} }),
  },
}))

const TEST_MODEL: Model = {
  model_id: 'openai/gpt-4o',
  name: 'GPT-4o',
  provider: 'openai',
  input_modalities: ['text'],
} as Model

function makeChat(overrides: Partial<Chat> = {}): Chat {
  return {
    id: 'chat-1',
    model: TEST_MODEL,
    messages: [],
    isLoading: false,
    parameters: getDefaultModelParameters(),
    ...overrides,
  } as Chat
}

/**
 * Minimal reducer harness for the `setChatGroups` state updater. useMessageSending
 * always calls it with an updater FUNCTION (React's functional setState form), never
 * a bare value — a plain vi.fn() would just record unusable function references.
 */
function makeChatGroupsHarness(initialChat: Chat) {
  let groups: any[] = [{ id: 'group-1', chats: [initialChat], updatedAt: new Date() }]
  const setChatGroups = vi.fn((updater: any) => {
    groups = typeof updater === 'function' ? updater(groups) : updater
  })
  return {
    setChatGroups,
    getChat: (): Chat => groups[0].chats.find((c: Chat) => c.id === initialChat.id),
  }
}

/** Captures the callbacks object useMessageSending hands to llmApi.completeStream. */
function mockCompleteStream() {
  let resolveStream: (() => void) | null = null
  let captured: any = null
  vi.mocked(llmApi.completeStream).mockImplementation((_payload, callbacks, _opts) => {
    captured = callbacks
    return new Promise<void>((resolve) => {
      resolveStream = () => resolve()
    })
  })
  return {
    getCallbacks: () => captured,
    finish: () => resolveStream?.(),
  }
}

function renderMessageSending(chat: Chat) {
  const harness = makeChatGroupsHarness(chat)
  const hook = renderHook(() =>
    useMessageSending({
      chats: [chat],
      activeGroupId: 'group-1',
      chatGroups: [{ id: 'group-1', chats: [chat] }],
      setChatGroups: harness.setChatGroups,
      attachments: [],
      setAttachments: vi.fn(),
      toast: vi.fn(),
      isAuthenticated: true,
      openModal: vi.fn(),
      getAuthModalVariant: vi.fn(() => 'default'),
    })
  )
  return { hook, harness }
}

const baseMessages: Message[] = [{ role: 'user', content: 'Hello there', timestamp: new Date() } as Message]

describe('useMessageSending — sendToModel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(conversationsAPI.createMessage).mockResolvedValue({ id: 'persisted-msg-1' } as any)
    vi.spyOn(useUsageQuotaStore.getState(), 'refreshAfterUsage').mockResolvedValue(undefined)
  })

  it('sends a request payload built from the model id, messages and streaming parameters', async () => {
    const chat = makeChat()
    const { hook } = renderMessageSending(chat)
    const stream = mockCompleteStream()

    act(() => {
      hook.result.current.sendToModel('chat-1', TEST_MODEL, baseMessages)
    })

    expect(llmApi.completeStream).toHaveBeenCalledTimes(1)
    const [payload] = vi.mocked(llmApi.completeStream).mock.calls[0]
    expect(payload.model).toBe('openai/gpt-4o')
    expect(payload.messages).toEqual([{ role: 'user', content: 'Hello there' }])
    expect(payload.stream).toBe(true) // enable_streaming default is true
    expect(payload.conversation_id).toBe('group-1')
    expect(payload.chat_id).toBe('chat-1')

    await act(async () => stream.finish())
  })

  it('sets the chat to isLoading before any content streams in', async () => {
    const chat = makeChat()
    const { hook, harness } = renderMessageSending(chat)
    const stream = mockCompleteStream()

    act(() => {
      hook.result.current.sendToModel('chat-1', TEST_MODEL, baseMessages)
    })

    expect(harness.getChat().isLoading).toBe(true)

    await act(async () => stream.finish())
  })

  it('accumulates onContent deltas into a single growing text step', async () => {
    const chat = makeChat()
    const { hook, harness } = renderMessageSending(chat)
    const stream = mockCompleteStream()

    act(() => {
      hook.result.current.sendToModel('chat-1', TEST_MODEL, baseMessages)
    })

    act(() => stream.getCallbacks().onContent('Hello'))
    act(() => stream.getCallbacks().onContent(', world'))

    const assistantMsg = harness.getChat().messages.find(m => m.role === 'assistant')!
    expect(assistantMsg.content).toBe('Hello, world')
    expect(assistantMsg.steps).toEqual([{ type: 'text', content: 'Hello, world' }])
    // Loading flips off as soon as the first content arrives.
    expect(harness.getChat().isLoading).toBe(false)

    await act(async () => stream.finish())
  })

  it('finalizes a reasoning step and starts a new text step once content begins streaming', async () => {
    const chat = makeChat()
    const { hook, harness } = renderMessageSending(chat)
    const stream = mockCompleteStream()

    act(() => {
      hook.result.current.sendToModel('chat-1', TEST_MODEL, baseMessages)
    })

    act(() => stream.getCallbacks().onReasoning('Thinking about it'))
    act(() => stream.getCallbacks().onContent('The answer is 42'))

    const assistantMsg = harness.getChat().messages.find(m => m.role === 'assistant')!
    expect(assistantMsg.steps).toEqual([
      { type: 'reasoning', content: 'Thinking about it', isStreaming: false },
      { type: 'text', content: 'The answer is 42' },
    ])
    expect(assistantMsg.is_reasoning).toBe(false)

    await act(async () => stream.finish())
  })

  it('records pending_approvals and tool_calls from onToolCallRequest', async () => {
    const chat = makeChat()
    const { hook, harness } = renderMessageSending(chat)
    const stream = mockCompleteStream()

    act(() => {
      hook.result.current.sendToModel('chat-1', TEST_MODEL, baseMessages)
    })

    const approvals = [{ id: 'appr-1', tool: 'web_search' }]
    const toolCalls = [{ id: 't1', type: 'function', function: { name: 'web_search', arguments: '{}' } }]
    act(() => stream.getCallbacks().onToolCallRequest(approvals, toolCalls))

    const assistantMsg = harness.getChat().messages.find(m => m.role === 'assistant')!
    expect(assistantMsg.tool_calls).toEqual(toolCalls)
    expect(assistantMsg.pending_approvals).toEqual(approvals)

    await act(async () => stream.finish())
  })

  it('onError before any content streamed adds a standalone error message and stops loading', async () => {
    const chat = makeChat()
    const { hook, harness } = renderMessageSending(chat)
    const stream = mockCompleteStream()

    act(() => {
      hook.result.current.sendToModel('chat-1', TEST_MODEL, baseMessages)
    })

    act(() => stream.getCallbacks().onError('insufficient_credits', 'Add funds', 'insufficient_credits'))

    const chatState = harness.getChat()
    expect(chatState.isLoading).toBe(false)
    const errMsg = chatState.messages.find(m => m.role === 'assistant')!
    expect(errMsg.isError).toBe(true)
    expect(errMsg.errorCode).toBe('insufficient_credits')
    expect(errMsg.is_interrupted).toBe(true)

    await act(async () => stream.finish())
  })

  it('onError after content has streamed marks the EXISTING streaming message as errored (does not duplicate)', async () => {
    const chat = makeChat()
    const { hook, harness } = renderMessageSending(chat)
    const stream = mockCompleteStream()

    act(() => {
      hook.result.current.sendToModel('chat-1', TEST_MODEL, baseMessages)
    })
    act(() => stream.getCallbacks().onContent('partial answer'))
    act(() => stream.getCallbacks().onError('boom', undefined, undefined))

    const chatState = harness.getChat()
    const assistantMessages = chatState.messages.filter(m => m.role === 'assistant')
    expect(assistantMessages).toHaveLength(1)
    expect(assistantMessages[0].isError).toBe(true)

    await act(async () => stream.finish())
  })

  it('a successful completion persists the assistant message via conversationsAPI.createMessage', async () => {
    const chat = makeChat()
    const { hook, harness } = renderMessageSending(chat)
    const stream = mockCompleteStream()

    await act(async () => {
      const promise = hook.result.current.sendToModel('chat-1', TEST_MODEL, baseMessages)
      stream.getCallbacks().onContent('Final answer')
      stream.getCallbacks().onDone({
        usage: { prompt_tokens: 10, completion_tokens: 5, total_tokens: 15 },
        cost: 0.002,
        prompt_cost: 0.001,
        completion_cost: 0.001,
        model: 'openai/gpt-4o',
        finish_reason: 'stop',
      })
      stream.finish()
      await promise
    })

    expect(conversationsAPI.createMessage).toHaveBeenCalledWith(
      'group-1',
      'chat-1',
      expect.objectContaining({ role: 'assistant', content: 'Final answer', model_id: 'openai/gpt-4o' })
    )
    const assistantMsg = harness.getChat().messages.find(m => m.role === 'assistant')!
    expect(assistantMsg.tokens).toEqual({ prompt: 10, completion: 5, total: 15 })
    expect(assistantMsg.cost).toBe(0.002)
    expect(harness.getChat().isLoading).toBe(false)
  })

  it('an AbortError persists partial content as stopped and does NOT show an error message', async () => {
    const chat = makeChat()
    const { hook, harness } = renderMessageSending(chat)
    let capturedCallbacks: any = null
    vi.mocked(llmApi.completeStream).mockImplementation(async (_payload, callbacks) => {
      capturedCallbacks = callbacks
      callbacks.onContent('partial before abort')
      const err = new Error('The user aborted a request.')
      err.name = 'AbortError'
      throw err
    })

    await act(async () => {
      await hook.result.current.sendToModel('chat-1', TEST_MODEL, baseMessages)
    })

    expect(capturedCallbacks).toBeTruthy()
    const chatState = harness.getChat()
    expect(chatState.isLoading).toBe(false)
    // No isError message was added for an abort.
    expect(chatState.messages.some(m => m.isError)).toBe(false)
    expect(conversationsAPI.createMessage).toHaveBeenCalledWith(
      'group-1',
      'chat-1',
      expect.objectContaining({ content: 'partial before abort', is_stopped: true })
    )
  })

  it('a non-abort thrown error surfaces a friendly error message in the chat and calls toast', async () => {
    const chat = makeChat()
    const harness = makeChatGroupsHarness(chat)
    const toast = vi.fn()
    const hook = renderHook(() =>
      useMessageSending({
        chats: [chat],
        activeGroupId: 'group-1',
        chatGroups: [{ id: 'group-1', chats: [chat] }],
        setChatGroups: harness.setChatGroups,
        attachments: [],
        setAttachments: vi.fn(),
        toast,
        isAuthenticated: true,
        openModal: vi.fn(),
        getAuthModalVariant: vi.fn(() => 'default'),
      })
    )
    vi.mocked(llmApi.completeStream).mockRejectedValue(new Error('Something went wrong'))

    await act(async () => {
      await hook.result.current.sendToModel('chat-1', TEST_MODEL, baseMessages)
    })

    const chatState = harness.getChat()
    expect(chatState.isLoading).toBe(false)
    const errMsg = chatState.messages.find(m => m.role === 'assistant')!
    expect(errMsg.isError).toBe(true)
    expect(errMsg.content).toMatch(/^Error: /)
    expect(toast).toHaveBeenCalledWith(expect.objectContaining({ title: 'Error', variant: 'destructive' }))
  })

  it('applies chat_memory limiting: only the last N message pairs are sent to the model', async () => {
    const chat = makeChat({ parameters: { ...getDefaultModelParameters(), chat_memory: 1 } })
    const { hook } = renderMessageSending(chat)
    const stream = mockCompleteStream()

    const manyMessages: Message[] = [
      { role: 'user', content: 'msg1', timestamp: new Date() } as Message,
      { role: 'assistant', content: 'reply1', timestamp: new Date() } as Message,
      { role: 'user', content: 'msg2', timestamp: new Date() } as Message,
      { role: 'assistant', content: 'reply2', timestamp: new Date() } as Message,
      { role: 'user', content: 'msg3 (latest)', timestamp: new Date() } as Message,
    ]

    act(() => {
      hook.result.current.sendToModel('chat-1', TEST_MODEL, manyMessages)
    })

    const [payload] = vi.mocked(llmApi.completeStream).mock.calls[0]
    // chat_memory: 1 keeps the last 1*2 = 2 messages.
    expect(payload.messages).toHaveLength(2)
    expect(payload.messages[payload.messages.length - 1].content).toBe('msg3 (latest)')

    await act(async () => stream.finish())
  })
})
