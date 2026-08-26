import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import type { SetStateAction } from 'react'
import { useMessageComposition } from '../useMessageComposition'
import { conversationsAPI } from '@/api/conversations'
import { uploadAttachmentsAsAssets, buildUnsupportedAttachmentsMessage } from '../attachmentAssets'
import type { Chat, ChatGroup, Model, ImageAttachment } from '@/components/models/types'

vi.mock('@/api/conversations', () => ({
  conversationsAPI: { createMessage: vi.fn().mockResolvedValue({ id: 'persisted-1' }) },
}))

vi.mock('../attachmentAssets', () => ({
  uploadAttachmentsAsAssets: vi.fn().mockResolvedValue({ enriched: [], assetRefs: [] }),
  buildUnsupportedAttachmentsMessage: vi.fn().mockReturnValue(null),
}))

vi.mock('../useConversationTitleGeneration', () => ({
  useConversationTitleGeneration: () => vi.fn(),
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

/** Minimal reducer harness for the functional-updater form of setChatGroups. */
function makeHarness(chat: Chat) {
  let groups: ChatGroup[] = [{ id: 'group-1', chats: [chat], isCustomName: true } as ChatGroup]
  const setChatGroups = vi.fn((updater: SetStateAction<ChatGroup[]>) => {
    groups = typeof updater === 'function' ? (updater as (prev: ChatGroup[]) => ChatGroup[])(groups) : updater
  })
  return { setChatGroups, getGroups: () => groups, getChat: () => groups[0].chats.find((c) => c.id === chat.id)! }
}

function renderComposition(chat: Chat, propOverrides: Partial<Parameters<typeof useMessageComposition>[0]> = {}) {
  const harness = makeHarness(chat)
  const sendToModel = vi.fn().mockResolvedValue(undefined)
  const toast = vi.fn()
  const openModal = vi.fn()
  const getAuthModalVariant = vi.fn(() => 'default')
  const addRecentChatModel = vi.fn()
  const setAttachments = vi.fn()
  const hook = renderHook(() =>
    useMessageComposition({
      chats: [chat],
      activeGroupId: 'group-1',
      chatGroups: harness.getGroups(),
      setChatGroups: harness.setChatGroups,
      attachments: [],
      setAttachments,
      toast,
      isAuthenticated: true,
      openModal,
      getAuthModalVariant,
      sendToModel,
      addRecentChatModel,
      ...propOverrides,
    })
  )
  return { hook, harness, sendToModel, toast, openModal, getAuthModalVariant, addRecentChatModel, setAttachments }
}

describe('useMessageComposition', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(uploadAttachmentsAsAssets).mockResolvedValue({ enriched: [], assetRefs: [] })
    vi.mocked(buildUnsupportedAttachmentsMessage).mockReturnValue(null)
  })

  describe('composeAndSend', () => {
    it('blocks unauthenticated senders and opens the auth modal instead of dispatching', async () => {
      const chat = makeChat()
      const { hook, sendToModel, toast, openModal } = renderComposition(chat, { isAuthenticated: false })

      await act(async () => {
        await hook.result.current.composeAndSend(['chat-1'], 'hello', [])
      })

      expect(toast).toHaveBeenCalledWith(expect.objectContaining({ title: 'Authentication required' }))
      expect(openModal).toHaveBeenCalled()
      expect(sendToModel).not.toHaveBeenCalled()
    })

    it('is a no-op for empty content, no attachments, and no tool continuation', async () => {
      const chat = makeChat()
      const { hook, sendToModel } = renderComposition(chat)

      await act(async () => {
        await hook.result.current.composeAndSend(['chat-1'], '', [])
      })

      expect(sendToModel).not.toHaveBeenCalled()
    })

    it('appends the user message to the target chat and dispatches it to sendToModel', async () => {
      const chat = makeChat()
      const { hook, harness, sendToModel } = renderComposition(chat)

      await act(async () => {
        await hook.result.current.composeAndSend(['chat-1'], 'hello there', [])
      })

      const userMsg = harness.getChat().messages.find((m) => m.role === 'user')!
      expect(userMsg.content).toBe('hello there')
      expect(sendToModel).toHaveBeenCalledWith('chat-1', TEST_MODEL, expect.any(Array))
    })

    it('persists the user message via conversationsAPI once dispatched', async () => {
      const chat = makeChat()
      const { hook } = renderComposition(chat)

      await act(async () => {
        await hook.result.current.composeAndSend(['chat-1'], 'hello there', [])
      })
      // Persistence runs fire-and-forget; flush its microtask.
      await act(async () => { await Promise.resolve() })

      expect(conversationsAPI.createMessage).toHaveBeenCalledWith(
        'group-1',
        'chat-1',
        expect.objectContaining({ role: 'user', content: 'hello there' })
      )
    })

    it('a tool continuation sends existing messages without appending a new user message', async () => {
      const chat = makeChat({ messages: [{ role: 'assistant', content: 'tool result', timestamp: new Date() }] })
      const { hook, harness, sendToModel } = renderComposition(chat)

      await act(async () => {
        await hook.result.current.composeAndSend(['chat-1'], '', [], true)
      })

      expect(harness.getChat().messages).toHaveLength(1)
      expect(sendToModel).toHaveBeenCalledWith('chat-1', TEST_MODEL, expect.any(Array))
    })

    it('appends an unsupported-attachments notice when buildUnsupportedAttachmentsMessage returns one', async () => {
      vi.mocked(buildUnsupportedAttachmentsMessage).mockReturnValue('This model does not support image inputs.')
      const chat = makeChat()
      const { hook, harness } = renderComposition(chat)
      const imageAttachment: ImageAttachment = {
        id: 'att-1',
        type: 'image',
        file: new File(['x'], 'photo.png', { type: 'image/png' }),
        preview: 'blob:preview',
      }

      await act(async () => {
        await hook.result.current.composeAndSend(['chat-1'], 'look at this', [imageAttachment])
      })

      const notice = harness.getChat().messages.find((m) => m.isUnsupported)
      expect(notice?.content).toBe('This model does not support image inputs.')
    })

    it('skips disabled or model-less chats entirely', async () => {
      const chat = makeChat({ disabled: true })
      const { hook, harness, sendToModel } = renderComposition(chat)

      await act(async () => {
        await hook.result.current.composeAndSend(['chat-1'], 'hello there', [])
      })

      expect(harness.getChat().messages).toHaveLength(0)
      expect(sendToModel).not.toHaveBeenCalled()
    })

    it('tracks the model as recently used for each dispatched chat', async () => {
      const chat = makeChat()
      const { hook, addRecentChatModel } = renderComposition(chat)

      await act(async () => {
        await hook.result.current.composeAndSend(['chat-1'], 'hello there', [])
      })

      expect(addRecentChatModel).toHaveBeenCalledWith('openai/gpt-4o', TEST_MODEL)
    })
  })

  describe('sendMessage', () => {
    it('snapshots current attachments with serialization-survival metadata, forwards them to composeAndSend, and clears them', () => {
      const chat = makeChat()
      const imageAttachment: ImageAttachment = {
        id: 'att-1',
        type: 'image',
        file: new File(['x'], 'photo.png', { type: 'image/png' }),
        preview: 'blob:preview',
      }
      const { hook, harness, setAttachments } = renderComposition(chat, { attachments: [imageAttachment] })

      act(() => {
        hook.result.current.sendMessage('hello')
      })

      // The File object itself doesn't survive JSON serialization; sendMessage must
      // lift its metadata onto the attachment's own fields before composeAndSend runs.
      const userMsg = harness.getChat().messages.find((m) => m.role === 'user')!
      const sentAttachment = userMsg.attachments?.[0] as ImageAttachment & { fileName?: string; fileType?: string; fileSize?: number }
      expect(sentAttachment).toMatchObject({ fileName: 'photo.png', fileType: 'image/png', fileSize: 1 })

      expect(setAttachments).toHaveBeenCalledWith([])
    })

    it('does nothing when no chat has a model assigned', () => {
      const chat = makeChat({ model: null })
      const { hook, setAttachments } = renderComposition(chat)

      act(() => {
        hook.result.current.sendMessage('hello')
      })

      expect(setAttachments).not.toHaveBeenCalled()
    })
  })
})
