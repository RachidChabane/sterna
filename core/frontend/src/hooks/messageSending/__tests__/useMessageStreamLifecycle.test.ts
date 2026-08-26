import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import type { SetStateAction } from 'react'
import { useMessageStreamLifecycle } from '../useMessageStreamLifecycle'
import { llmApi, type CodingAgentQuestion } from '@/api/llm'
import { conversationsAPI } from '@/api/conversations'
import type { APIMessage } from '@/api/conversations'
import type { StreamCallbacks } from '../streamCallbacks'
import type { Chat, ChatGroup, Message, Model } from '@/components/models/types'

function makeApiMessage(overrides: Partial<APIMessage> = {}): APIMessage {
  return {
    id: 'persisted-1',
    chat: 'chat-1',
    role: 'assistant',
    content: { text: '' },
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
    ...overrides,
  }
}

vi.mock('@/api/llm', () => ({
  llmApi: {
    completeStream: vi.fn(),
    getGenerationUsage: vi.fn().mockResolvedValue({ usage: { prompt_tokens: 0, completion_tokens: 0 }, cost: 0 }),
  },
}))

vi.mock('@/api/conversations', () => ({
  conversationsAPI: {
    createMessage: vi.fn().mockResolvedValue({ id: 'persisted-1' }),
    updateMessage: vi.fn().mockResolvedValue({}),
  },
}))

vi.mock('@/api/sparks', () => ({
  sparksAPI: { createBatch: vi.fn().mockResolvedValue([]) },
}))

vi.mock('@/api/codeSession', () => ({
  codeSessionApi: { sendCodingAgentAnswer: vi.fn().mockResolvedValue({}) },
}))

const TEST_MODEL: Model = {
  model_id: 'openai/gpt-4o',
  name: 'GPT-4o',
  provider: 'openai',
  input_modalities: ['text'],
} as Model

function makeChat(overrides: Partial<Chat> = {}): Chat {
  return { id: 'chat-1', model: TEST_MODEL, messages: [], isLoading: false, ...overrides } as Chat
}

function makeHarness(chat: Chat) {
  let groups: ChatGroup[] = [{ id: 'group-1', chats: [chat] } as ChatGroup]
  const setChatGroups = vi.fn((updater: SetStateAction<ChatGroup[]>) => {
    groups = typeof updater === 'function' ? (updater as (prev: ChatGroup[]) => ChatGroup[])(groups) : updater
  })
  return { setChatGroups, getChat: () => groups[0].chats.find((c) => c.id === chat.id)! }
}

function mockCompleteStream() {
  let resolveStream: (() => void) | null = null
  let captured: StreamCallbacks | null = null
  vi.mocked(llmApi.completeStream).mockImplementation((_payload, callbacks) => {
    captured = callbacks
    return new Promise<void>((resolve) => { resolveStream = () => resolve() })
  })
  return { getCallbacks: () => captured!, finish: () => resolveStream?.() }
}

function renderLifecycle(chat: Chat) {
  const harness = makeHarness(chat)
  const refreshQuotaAfterUsage = vi.fn().mockResolvedValue(undefined)
  const pendingCodingAgentQuestionRef: { current: CodingAgentQuestion | null } = { current: null }
  const setPendingQuestionVersion = vi.fn()
  const hook = renderHook(() =>
    useMessageStreamLifecycle({
      chats: [chat],
      activeGroupId: 'group-1',
      setChatGroups: harness.setChatGroups,
      toast: vi.fn(),
      streamResponsesSetting: true,
      voiceConversationActive: false,
      refreshQuotaAfterUsage,
      pendingCodingAgentQuestionRef,
      setPendingQuestionVersion,
    })
  )
  return { hook, harness, refreshQuotaAfterUsage, pendingCodingAgentQuestionRef, setPendingQuestionVersion }
}

const baseMessages: Message[] = [{ role: 'user', content: 'Hello there', timestamp: new Date() } as Message]

describe('useMessageStreamLifecycle', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(conversationsAPI.createMessage).mockResolvedValue(makeApiMessage())
  })

  it('builds a streaming request payload from the model, messages, and streaming setting', async () => {
    const chat = makeChat()
    const { hook } = renderLifecycle(chat)
    const stream = mockCompleteStream()

    act(() => {
      hook.result.current.sendToModel('chat-1', TEST_MODEL, baseMessages)
    })

    const [payload] = vi.mocked(llmApi.completeStream).mock.calls[0]
    expect(payload.model).toBe('openai/gpt-4o')
    expect(payload.messages).toEqual([{ role: 'user', content: 'Hello there' }])
    expect(payload.stream).toBe(true)

    await act(async () => stream.finish())
  })

  it('sets isLoading true immediately and registers an abort controller', async () => {
    const chat = makeChat()
    const { hook, harness } = renderLifecycle(chat)
    const stream = mockCompleteStream()

    act(() => {
      hook.result.current.sendToModel('chat-1', TEST_MODEL, baseMessages)
    })

    expect(harness.getChat().isLoading).toBe(true)
    expect(hook.result.current.abortControllersRef.current.has('chat-1')).toBe(true)

    await act(async () => stream.finish())
    expect(hook.result.current.abortControllersRef.current.has('chat-1')).toBe(false)
  })

  it('clears the pending coding agent question ref on completion and refreshes quota', async () => {
    const chat = makeChat()
    const { hook, refreshQuotaAfterUsage, pendingCodingAgentQuestionRef, setPendingQuestionVersion } = renderLifecycle(chat)
    pendingCodingAgentQuestionRef.current = { question: 'Proceed?' }
    const stream = mockCompleteStream()

    await act(async () => {
      const promise = hook.result.current.sendToModel('chat-1', TEST_MODEL, baseMessages)
      stream.getCallbacks().onContent('answer')
      stream.getCallbacks().onDone({
        usage: { prompt_tokens: 1, completion_tokens: 1, total_tokens: 2 },
        model: 'openai/gpt-4o',
        finish_reason: 'stop',
      })
      stream.finish()
      await promise
    })

    expect(pendingCodingAgentQuestionRef.current).toBeNull()
    expect(setPendingQuestionVersion).toHaveBeenCalled()
    expect(refreshQuotaAfterUsage).toHaveBeenCalled()
  })

  it('persists partial content as stopped on an AbortError without recording an error message', async () => {
    const chat = makeChat()
    const { hook, harness } = renderLifecycle(chat)
    vi.mocked(llmApi.completeStream).mockImplementation(async (_payload, callbacks) => {
      callbacks.onContent('partial before abort')
      const err = new Error('The user aborted a request.')
      err.name = 'AbortError'
      throw err
    })

    await act(async () => {
      await hook.result.current.sendToModel('chat-1', TEST_MODEL, baseMessages)
    })

    expect(harness.getChat().isLoading).toBe(false)
    expect(harness.getChat().messages.some((m) => m.isError)).toBe(false)
    expect(conversationsAPI.createMessage).toHaveBeenCalledWith(
      'group-1',
      'chat-1',
      expect.objectContaining({ content: 'partial before abort', is_stopped: true })
    )
  })
})
