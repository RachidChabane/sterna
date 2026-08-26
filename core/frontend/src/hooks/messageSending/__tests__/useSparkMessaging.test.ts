import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import type { SetStateAction } from 'react'
import { useSparkMessaging } from '../useSparkMessaging'
import { sparksAPI, type Spark } from '@/api/sparks'
import type { Chat, ChatGroup, Message, Model } from '@/components/models/types'

vi.mock('@/api/sparks', () => ({
  sparksAPI: { get: vi.fn() },
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

function makeSpark(overrides: Partial<Spark> = {}): Spark {
  return {
    id: 'spark-1',
    title: 'My Spark',
    framework: 'react',
    code: '',
    dependencies: [],
    is_ignited: false,
    version: 1,
    parent_id: null,
    chat_id: 'chat-1',
    chat_name: null,
    conversation_id: 'group-1',
    message_id: null,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    ...overrides,
  }
}

/** Minimal reducer harness for the functional-updater form of setChatGroups. */
function makeHarness(chat: Chat) {
  let groups: ChatGroup[] = [{ id: 'group-1', chats: [chat] } as ChatGroup]
  const setChatGroups = vi.fn((updater: SetStateAction<ChatGroup[]>) => {
    groups = typeof updater === 'function' ? (updater as (prev: ChatGroup[]) => ChatGroup[])(groups) : updater
  })
  return { setChatGroups, getChat: () => groups[0].chats.find((c) => c.id === chat.id)! }
}

function renderSparkMessaging(chat: Chat, sendToModel = vi.fn().mockResolvedValue(undefined)) {
  const harness = makeHarness(chat)
  const hook = renderHook(() =>
    useSparkMessaging({ chats: [chat], activeGroupId: 'group-1', setChatGroups: harness.setChatGroups, sendToModel })
  )
  return { hook, harness, sendToModel }
}

describe('useSparkMessaging', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('sendSparkFixMessage', () => {
    it('appends the fix-request content as a user message before dispatching', async () => {
      const chat = makeChat()
      const { hook, harness } = renderSparkMessaging(chat)

      await act(async () => {
        await hook.result.current.sendSparkFixMessage('chat-1', 'please fix this', {
          spark_id: 'spark-1',
          spark_title: 'My Spark',
          error: 'boom',
        })
      })

      const userMsg = harness.getChat().messages.find((m) => m.role === 'user')!
      expect(userMsg.content).toBe('please fix this')
    })

    it('forwards sparkFixRequest and forces enable_sparks on', async () => {
      const chat = makeChat()
      const { hook, sendToModel } = renderSparkMessaging(chat)
      const sparkFixRequest = { spark_id: 'spark-1', spark_title: 'My Spark', error: 'boom' }

      await act(async () => {
        await hook.result.current.sendSparkFixMessage('chat-1', 'please fix this', sparkFixRequest)
      })

      expect(sendToModel).toHaveBeenCalledWith(
        'chat-1',
        TEST_MODEL,
        expect.any(Array),
        { sparkFixRequest, parameterOverrides: { enable_sparks: true } }
      )
    })

    it('does nothing when the chat has no model', async () => {
      const chat = makeChat({ model: null })
      const { hook, sendToModel } = renderSparkMessaging(chat)

      await act(async () => {
        await hook.result.current.sendSparkFixMessage('chat-1', 'x', { spark_id: 's', spark_title: 't', error: 'e' })
      })

      expect(sendToModel).not.toHaveBeenCalled()
    })
  })

  describe('sendIgniteMessage', () => {
    it('sends an ignite request with sparks and file tools enabled', async () => {
      const chat = makeChat()
      const { hook, sendToModel } = renderSparkMessaging(chat)
      const sparkIgniteRequest = { spark_id: 'spark-1', spark_title: 'My Spark' }
      vi.mocked(sparksAPI.get).mockResolvedValue(makeSpark({ is_ignited: false }))

      await act(async () => {
        await hook.result.current.sendIgniteMessage('chat-1', sparkIgniteRequest)
      })

      expect(sendToModel).toHaveBeenCalledWith(
        'chat-1',
        TEST_MODEL,
        expect.any(Array),
        { sparkIgniteRequest, parameterOverrides: { enable_sparks: true, enable_file_tools: true } }
      )
    })

    it('marks the matching spark as ignited once sparksAPI confirms is_ignited', async () => {
      const assistantMessage: Message = {
        role: 'assistant',
        content: '',
        timestamp: new Date(),
        sparks: [{ id: 'spark-1', title: 'My Spark', framework: 'react', code: '', version: 1, is_ignited: false }],
      }
      const chat = makeChat({ messages: [assistantMessage] })
      const { hook, harness } = renderSparkMessaging(chat)
      vi.mocked(sparksAPI.get).mockResolvedValue(makeSpark({ is_ignited: true }))

      await act(async () => {
        await hook.result.current.sendIgniteMessage('chat-1', { spark_id: 'spark-1', spark_title: 'My Spark' })
      })

      const sparks = harness.getChat().messages.flatMap((m) => m.sparks ?? [])
      expect(sparks.find((s) => s.id === 'spark-1')?.is_ignited).toBe(true)
    })

    it('does not throw when sparksAPI.get rejects after a successful send', async () => {
      const chat = makeChat()
      const { hook } = renderSparkMessaging(chat)
      vi.mocked(sparksAPI.get).mockRejectedValue(new Error('network error'))

      await expect(
        act(async () => {
          await hook.result.current.sendIgniteMessage('chat-1', { spark_id: 'spark-1', spark_title: 'My Spark' })
        })
      ).resolves.not.toThrow()
    })
  })
})
