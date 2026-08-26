import { describe, it, expect, vi } from 'vitest'
import { renderHook } from '@testing-library/react'
import { useRef } from 'react'
import { useChatHandlerMaps } from '../useChatHandlerMaps'
import type { Chat } from '../../types'

function makeChat(overrides: Partial<Chat> = {}): Chat {
  return {
    id: 'chat-1',
    model: null,
    messages: [],
    isLoading: false,
    parameters: {} as Chat['parameters'],
    ...overrides,
  }
}

function renderHandlerMaps(chats: Chat[], overrides: Partial<Parameters<typeof useChatHandlerMaps>[0]> = {}) {
  const base = {
    composeAndSend: vi.fn().mockResolvedValue(undefined),
    sendToModel: vi.fn(),
    updateChatModel: vi.fn(),
    updateChatMessages: vi.fn(),
    updateChatParameters: vi.fn(),
    updateChatDisabled: vi.fn(),
    updateChatHidden: vi.fn(),
    moveLeft: vi.fn(),
    moveRight: vi.fn(),
    clearChat: vi.fn(),
    cancelChat: vi.fn(),
    toast: vi.fn(),
    onRequestRemoveChat: vi.fn(),
    ...overrides,
  }
  const initialProps = { chats, ...base }
  const rendered = renderHook(
    (props: { chats: Chat[] } & typeof base) => {
      const chatsRef = useRef(props.chats)
      chatsRef.current = props.chats
      return useChatHandlerMaps({ ...props, chatsRef })
    },
    { initialProps }
  )
  return { ...rendered, initialProps }
}

describe('useChatHandlerMaps', () => {
  it('returns the same per-chat handler reference across a no-op re-render', () => {
    const { result, rerender, initialProps } = renderHandlerMaps([makeChat()])
    const first = result.current.getSendMessageHandler('chat-1')
    rerender(initialProps)
    expect(result.current.getSendMessageHandler('chat-1')).toBe(first)
  })

  it('clears the send-message cache when composeAndSend changes identity', () => {
    const { result, rerender } = renderHandlerMaps([makeChat()])
    const first = result.current.getSendMessageHandler('chat-1')
    rerender({ chats: [makeChat()], composeAndSend: vi.fn().mockResolvedValue(undefined) } as never)
    expect(result.current.getSendMessageHandler('chat-1')).not.toBe(first)
  })

  it('clears the model-select cache when updateChatModel changes identity', () => {
    const { result, rerender } = renderHandlerMaps([makeChat()])
    const first = result.current.getModelSelectHandler('chat-1')
    rerender({ chats: [makeChat()], updateChatModel: vi.fn() } as never)
    expect(result.current.getModelSelectHandler('chat-1')).not.toBe(first)
  })

  it('clears the update-messages cache when updateChatMessages changes identity', () => {
    const { result, rerender } = renderHandlerMaps([makeChat()])
    const first = result.current.getUpdateMessagesHandler('chat-1')
    rerender({ chats: [makeChat()], updateChatMessages: vi.fn() } as never)
    expect(result.current.getUpdateMessagesHandler('chat-1')).not.toBe(first)
  })

  it('getSendMessageHandler composes and sends to only its own chat id', async () => {
    const composeAndSend = vi.fn().mockResolvedValue(undefined)
    const { result } = renderHandlerMaps([makeChat({ id: 'chat-9' })], { composeAndSend })
    await result.current.getSendMessageHandler('chat-9')('hello', [])
    expect(composeAndSend).toHaveBeenCalledWith(['chat-9'], 'hello', [])
  })

  it('sendToAllChatsHandler warns via toast and skips composeAndSend when no chat has a model', async () => {
    const composeAndSend = vi.fn().mockResolvedValue(undefined)
    const toast = vi.fn()
    const { result } = renderHandlerMaps([makeChat({ model: null })], { composeAndSend, toast })
    await result.current.sendToAllChatsHandler('hello')
    expect(composeAndSend).not.toHaveBeenCalled()
    expect(toast).toHaveBeenCalledWith(expect.objectContaining({ variant: 'destructive' }))
  })

  it('sendToAllChatsHandler sends to every enabled, non-disabled chat', async () => {
    const composeAndSend = vi.fn().mockResolvedValue(undefined)
    const model = { model_id: 'gpt-5' } as Chat['model']
    const chats = [
      makeChat({ id: 'a', model }),
      makeChat({ id: 'b', model, disabled: true }),
      makeChat({ id: 'c', model: null }),
    ]
    const { result } = renderHandlerMaps(chats, { composeAndSend })
    await result.current.sendToAllChatsHandler('hello')
    expect(composeAndSend).toHaveBeenCalledWith(['a'], 'hello', [])
  })

  it('getToolExecutedHandler appends a tool message and continues the conversation when the chat has a model', () => {
    const model = { model_id: 'gpt-5' } as Chat['model']
    const chat = makeChat({ id: 'chat-1', model, messages: [] })
    const updateChatMessages = vi.fn()
    const sendToModel = vi.fn()
    const { result } = renderHandlerMaps([chat], { updateChatMessages, sendToModel })
    result.current.getToolExecutedHandler('chat-1')('call-1', 'search', { content: 'result text' })
    expect(updateChatMessages).toHaveBeenCalledTimes(1)
    const [, updatedMessages] = updateChatMessages.mock.calls[0]
    expect(updatedMessages).toHaveLength(1)
    expect(updatedMessages[0]).toMatchObject({ role: 'tool', tool_call_id: 'call-1' })
    expect(sendToModel).toHaveBeenCalledWith('chat-1', model, updatedMessages)
  })

  it('getToolExecutedHandler does nothing when the chat is no longer present', () => {
    const updateChatMessages = vi.fn()
    const sendToModel = vi.fn()
    const { result } = renderHandlerMaps([makeChat({ id: 'chat-1' })], { updateChatMessages, sendToModel })
    result.current.getToolExecutedHandler('missing-chat')('call-1', 'search', undefined)
    expect(updateChatMessages).not.toHaveBeenCalled()
    expect(sendToModel).not.toHaveBeenCalled()
  })

  it('getCancelChatHandler and getClearChatHandler delegate to the passed-in per-chat callbacks', () => {
    const cancelChat = vi.fn()
    const clearChat = vi.fn()
    const { result } = renderHandlerMaps([makeChat({ id: 'chat-1' })], { cancelChat, clearChat })
    result.current.getCancelChatHandler('chat-1')()
    result.current.getClearChatHandler('chat-1')(true)
    expect(cancelChat).toHaveBeenCalledWith('chat-1')
    expect(clearChat).toHaveBeenCalledWith('chat-1', true)
  })
})
