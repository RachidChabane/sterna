/**
 * Message-mutation handlers that rewind and resend part of a chat: retrying
 * a single assistant response, editing a user message (full rewind from that
 * point), and resending the last user message after a failed exchange. Each
 * deletes the affected messages from the database (when persisted) before
 * updating local state and triggering a resend.
 */
import { useCallback } from 'react'
import { conversationsAPI } from '@/api/conversations'
import { extractTextFromContent } from '@/utils/chatUtils'
import type { Attachment, Message } from '../types'
import type { useToast } from '@/hooks/use-toast'

type ToastFn = ReturnType<typeof useToast>['toast']

interface UseMessageMutationsParams {
  messages: Message[]
  onUpdateMessages?: (messages: Message[]) => void
  onSendMessage: (content: string, attachments?: Attachment[]) => void
  conversationId?: string
  currentChatId?: string
  toast: ToastFn
  setSuppressInterruptedWarning: (value: boolean) => void
}

export function useMessageMutations({
  messages,
  onUpdateMessages,
  onSendMessage,
  conversationId,
  currentChatId,
  toast,
  setSuppressInterruptedWarning,
}: UseMessageMutationsParams) {
  const handleRetry = useCallback(async (assistantMessageIndex: number) => {
    if (!onUpdateMessages) return

    // Find the closest preceding user message (skip any assistant notices)
    let userMessageIndex = -1
    for (let i = assistantMessageIndex - 1; i >= 0; i--) {
      if (messages[i].role === 'user') { userMessageIndex = i; break }
    }

    if (userMessageIndex < 0) {
      toast({ title: 'Cannot retry', description: 'No user message found before this response', variant: 'destructive' })
      return
    }

    const userMessage = messages[userMessageIndex]
    const userMessageText = extractTextFromContent(userMessage.content)
    const userAttachments = (userMessage.attachments || []) as Attachment[]

    // Remove the user message, the selected assistant message, and any assistant notices between them
    const toRemove = new Set<number>([userMessageIndex, assistantMessageIndex])
    for (let i = userMessageIndex + 1; i < assistantMessageIndex; i++) {
      const m = messages[i]
      if (m.role === 'assistant' && m.isUnsupported) toRemove.add(i)
    }
    const updatedMessages = messages.filter((_, idx) => !toRemove.has(idx))

    // Delete removed messages from the database (if they have message_id)
    if (conversationId && currentChatId) {
      const messagesToDelete = messages.filter((_, idx) => toRemove.has(idx))
      await Promise.all(
        messagesToDelete
          .filter(m => m.message_id)
          .map(m => conversationsAPI.deleteMessage(conversationId, currentChatId, m.message_id!).catch(err => {
            console.error('Failed to delete message from database:', err)
          }))
      )
    }

    // Update messages first
    onUpdateMessages(updatedMessages)

    // Wait for React to apply the state update before resending
    // This prevents a race condition where the new message would be added to the old state
    await new Promise(resolve => setTimeout(resolve, 0))

    // Prevent transient interrupted banner while retry triggers send
    setSuppressInterruptedWarning(true)

    // Then resend the user message (text + attachments if any)
    await onSendMessage(userMessageText, userAttachments.length ? userAttachments : undefined)
  }, [messages, onUpdateMessages, onSendMessage, toast, conversationId, currentChatId, setSuppressInterruptedWarning])

  const handleEditMessage = useCallback(async (messageIndex: number, content: string) => {
    if (!onUpdateMessages) return

    // Get the message being edited
    const editedMessage = messages[messageIndex]
    if (!editedMessage || editedMessage.role !== 'user') return

    // Get attachments from the message being edited
    const userAttachments = (editedMessage.attachments || []) as Attachment[]

    // Delete ALL messages from the edited message onwards (complete rewind)
    const messagesToDelete = messages.slice(messageIndex)
    const updatedMessages = messages.slice(0, messageIndex)

    // Delete removed messages from the database (if they have message_id)
    if (conversationId && currentChatId) {
      await Promise.all(
        messagesToDelete
          .filter(m => m.message_id)
          .map(m => conversationsAPI.deleteMessage(conversationId, currentChatId, m.message_id!).catch(err => {
            console.error('Failed to delete message from database:', err)
          }))
      )
    }

    // Update messages to remove everything from the edited message onwards
    onUpdateMessages(updatedMessages)

    // Wait for React to apply the state update
    await new Promise(resolve => setTimeout(resolve, 0))

    // Send the edited message as a new message
    await onSendMessage(content, userAttachments.length ? userAttachments : undefined)
  }, [messages, onUpdateMessages, onSendMessage, conversationId, currentChatId])

  const handleResend = useCallback(async (message: string) => {
    if (!onUpdateMessages) return

    // Find the last user message and its index
    let userMessageIndex = -1
    for (let i = messages.length - 1; i >= 0; i--) {
      if (messages[i].role === 'user') {
        userMessageIndex = i
        break
      }
    }

    if (userMessageIndex < 0) return

    // Get attachments from the original user message
    const userMessage = messages[userMessageIndex]
    const userAttachments = (userMessage.attachments || []) as Attachment[]

    // Remove the user message and any assistant messages after it (including interrupted/errored ones)
    const messagesToDelete = messages.slice(userMessageIndex)
    const updatedMessages = messages.slice(0, userMessageIndex)

    // Delete removed messages from the database (if they have message_id)
    if (conversationId && currentChatId) {
      await Promise.all(
        messagesToDelete
          .filter(m => m.message_id)
          .map(m => conversationsAPI.deleteMessage(conversationId, currentChatId, m.message_id!).catch(err => {
            console.error('Failed to delete message from database:', err)
          }))
      )
    }

    // Update messages first to remove the failed exchange
    onUpdateMessages(updatedMessages)

    // Suppress the warning while resending
    setSuppressInterruptedWarning(true)

    // Use setTimeout to ensure React has applied the state update before resending
    setTimeout(() => {
      onSendMessage(message, userAttachments.length ? userAttachments : undefined)
    }, 0)
  }, [messages, onUpdateMessages, onSendMessage, conversationId, currentChatId, setSuppressInterruptedWarning])

  return { handleRetry, handleEditMessage, handleResend }
}
