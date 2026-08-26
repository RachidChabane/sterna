import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'

const deleteMessage = vi.fn()

vi.mock('@/api/conversations', () => ({
  conversationsAPI: {
    deleteMessage: (...args: unknown[]) => deleteMessage(...args),
  },
}))

import { useMessageMutations } from '../useMessageMutations'
import type { Message } from '../../types'

function makeMessage(overrides: Partial<Message> = {}): Message {
  return {
    role: 'user',
    content: 'hi',
    timestamp: new Date('2026-01-01T00:00:00Z'),
    ...overrides,
  } as Message
}

describe('useMessageMutations', () => {
  const toast = vi.fn()
  const setSuppressInterruptedWarning = vi.fn()

  beforeEach(() => {
    deleteMessage.mockReset().mockResolvedValue(undefined)
    toast.mockReset()
    setSuppressInterruptedWarning.mockReset()
  })

  describe('handleRetry', () => {
    it('toasts and does nothing when no preceding user message exists', async () => {
      const onUpdateMessages = vi.fn()
      const onSendMessage = vi.fn()
      const messages = [makeMessage({ role: 'assistant', content: 'orphan' })]
      const { result } = renderHook(() => useMessageMutations({
        messages, onUpdateMessages, onSendMessage, toast, setSuppressInterruptedWarning,
      }))

      await act(async () => { await result.current.handleRetry(0) })

      expect(toast).toHaveBeenCalledWith(expect.objectContaining({ title: 'Cannot retry' }))
      expect(onUpdateMessages).not.toHaveBeenCalled()
    })

    it('removes the user+assistant pair and resends the user message', async () => {
      const onUpdateMessages = vi.fn()
      const onSendMessage = vi.fn()
      const messages = [
        makeMessage({ role: 'user', content: 'question', message_id: 'm1' }),
        makeMessage({ role: 'assistant', content: 'answer', message_id: 'm2' }),
      ]
      const { result } = renderHook(() => useMessageMutations({
        messages, onUpdateMessages, onSendMessage,
        conversationId: 'conv-1', currentChatId: 'chat-1',
        toast, setSuppressInterruptedWarning,
      }))

      await act(async () => { await result.current.handleRetry(1) })

      expect(deleteMessage).toHaveBeenCalledWith('conv-1', 'chat-1', 'm1')
      expect(deleteMessage).toHaveBeenCalledWith('conv-1', 'chat-1', 'm2')
      expect(onUpdateMessages).toHaveBeenCalledWith([])
      expect(setSuppressInterruptedWarning).toHaveBeenCalledWith(true)
      expect(onSendMessage).toHaveBeenCalledWith('question', undefined)
    })
  })

  describe('handleEditMessage', () => {
    it('rewinds from the edited message and sends the new content', async () => {
      const onUpdateMessages = vi.fn()
      const onSendMessage = vi.fn()
      const messages = [
        makeMessage({ role: 'user', content: 'first', message_id: 'm1' }),
        makeMessage({ role: 'assistant', content: 'reply', message_id: 'm2' }),
      ]
      const { result } = renderHook(() => useMessageMutations({
        messages, onUpdateMessages, onSendMessage, toast, setSuppressInterruptedWarning,
      }))

      await act(async () => { await result.current.handleEditMessage(0, 'edited text') })

      expect(onUpdateMessages).toHaveBeenCalledWith([])
      expect(onSendMessage).toHaveBeenCalledWith('edited text', undefined)
    })

    it('does nothing when the targeted message is not from the user', async () => {
      const onUpdateMessages = vi.fn()
      const onSendMessage = vi.fn()
      const messages = [makeMessage({ role: 'assistant', content: 'reply' })]
      const { result } = renderHook(() => useMessageMutations({
        messages, onUpdateMessages, onSendMessage, toast, setSuppressInterruptedWarning,
      }))

      await act(async () => { await result.current.handleEditMessage(0, 'edited') })

      expect(onSendMessage).not.toHaveBeenCalled()
    })
  })

  describe('handleResend', () => {
    it('removes the failed exchange and resends with a suppression flag', async () => {
      vi.useFakeTimers()
      const onUpdateMessages = vi.fn()
      const onSendMessage = vi.fn()
      const messages = [
        makeMessage({ role: 'user', content: 'question', message_id: 'm1' }),
        makeMessage({ role: 'assistant', content: '', isError: true, message_id: 'm2' } as Partial<Message>),
      ]
      const { result } = renderHook(() => useMessageMutations({
        messages, onUpdateMessages, onSendMessage, toast, setSuppressInterruptedWarning,
      }))

      await act(async () => {
        await result.current.handleResend('question')
        await vi.runAllTimersAsync()
      })

      expect(onUpdateMessages).toHaveBeenCalledWith([])
      expect(setSuppressInterruptedWarning).toHaveBeenCalledWith(true)
      expect(onSendMessage).toHaveBeenCalledWith('question', undefined)
      vi.useRealTimers()
    })

    it('does nothing when there is no user message to resend', async () => {
      const onUpdateMessages = vi.fn()
      const onSendMessage = vi.fn()
      const { result } = renderHook(() => useMessageMutations({
        messages: [], onUpdateMessages, onSendMessage, toast, setSuppressInterruptedWarning,
      }))

      await act(async () => { await result.current.handleResend('question') })

      expect(onUpdateMessages).not.toHaveBeenCalled()
    })
  })

  describe('handler identity stability', () => {
    it('keeps the same handler references across a no-op re-render, so the memoized chat context does not churn', () => {
      const messages = [makeMessage({ message_id: 'm1' })]
      const props = {
        messages, onUpdateMessages: vi.fn(), onSendMessage: vi.fn(),
        toast, setSuppressInterruptedWarning,
      }
      const { result, rerender } = renderHook((p) => useMessageMutations(p), { initialProps: props })

      const before = {
        handleRetry: result.current.handleRetry,
        handleEditMessage: result.current.handleEditMessage,
        handleResend: result.current.handleResend,
      }

      rerender(props)

      expect(result.current.handleRetry).toBe(before.handleRetry)
      expect(result.current.handleEditMessage).toBe(before.handleEditMessage)
      expect(result.current.handleResend).toBe(before.handleResend)
    })
  })
})
