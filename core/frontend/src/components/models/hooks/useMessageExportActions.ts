/**
 * Copy/export actions for a chat panel: per-message content and metadata,
 * plus whole-chat responses and metadata. Every action reads from the
 * current messages/model and reports success through the shared toast.
 */
import { useCallback } from 'react'
import { buildChatMetadata, buildChatResponsesText, extractTextFromContent, generateFilename } from '@/utils/chatUtils'
import type { Message, Model } from '../types'
import type { useToast } from '@/hooks/use-toast'

type ToastFn = ReturnType<typeof useToast>['toast']

interface UseMessageExportActionsParams {
  messages: Message[]
  model: Model | null
  toast: ToastFn
}

function messageMetadata(message: Message) {
  return {
    model: message.model,
    model_id: message.model_id,
    provider: message.provider,
    timestamp: message.timestamp,
    cost: message.cost,
    prompt_cost: message.prompt_cost,
    completion_cost: message.completion_cost,
    latency: message.latency,
    tokens: message.tokens,
  }
}

function downloadBlob(content: BlobPart, type: string, filename: string) {
  const blob = new Blob([content], { type })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

export function useMessageExportActions({ messages, model, toast }: UseMessageExportActionsParams) {
  const copyMessageContent = useCallback((content: Message['content']) => {
    const text = extractTextFromContent(content)
    navigator.clipboard.writeText(text)
    toast({
      title: 'Copied',
      description: 'Response copied to clipboard'
    })
  }, [toast])

  const copyMessageMetadata = useCallback((message: Message) => {
    navigator.clipboard.writeText(JSON.stringify(messageMetadata(message), null, 2))
    toast({
      title: 'Copied',
      description: 'Metadata copied to clipboard'
    })
  }, [toast])

  const exportMessageContent = useCallback((content: Message['content'], model?: string) => {
    const text = extractTextFromContent(content)
    const modelName = model ? model.replace(/[^a-zA-Z0-9-]/g, '_') : 'unknown'
    downloadBlob(text, 'text/plain', generateFilename(`response-${modelName}`, 'txt'))
    toast({
      title: 'Exported',
      description: 'Response exported as text file'
    })
  }, [toast])

  const exportMessageMetadata = useCallback((message: Message) => {
    const modelName = message.model ? message.model.replace(/[^a-zA-Z0-9-]/g, '_') : 'unknown'
    downloadBlob(JSON.stringify(messageMetadata(message), null, 2), 'application/json', generateFilename(`metadata-${modelName}`, 'json'))
    toast({
      title: 'Exported',
      description: 'Metadata exported as JSON file'
    })
  }, [toast])

  // Chat-level functions
  const copyChatResponses = useCallback(() => {
    const text = buildChatResponsesText(messages)
    navigator.clipboard.writeText(text)
    toast({
      title: 'Copied',
      description: 'All responses copied to clipboard'
    })
  }, [messages, toast])

  const copyChatMetadata = useCallback(() => {
    const metadata = buildChatMetadata(messages)
    navigator.clipboard.writeText(JSON.stringify(metadata, null, 2))
    toast({
      title: 'Copied',
      description: 'All metadata copied to clipboard'
    })
  }, [messages, toast])

  const exportChatResponses = useCallback(() => {
    const text = buildChatResponsesText(messages)
    const modelName = model?.name ? model.name.replace(/[^a-zA-Z0-9-]/g, '_') : 'unknown'
    downloadBlob(text, 'text/plain', generateFilename(`chat-${modelName}`, 'txt'))
    toast({
      title: 'Exported',
      description: 'All responses exported'
    })
  }, [messages, model, toast])

  const exportChatMetadata = useCallback(() => {
    const assistantMessages = messages.filter(m => m.role === 'assistant')
    const metadata = assistantMessages.map(messageMetadata)
    const modelName = model?.name ? model.name.replace(/[^a-zA-Z0-9-]/g, '_') : 'unknown'
    downloadBlob(JSON.stringify(metadata, null, 2), 'application/json', generateFilename(`chat-metadata-${modelName}`, 'json'))
    toast({
      title: 'Exported',
      description: 'All metadata exported'
    })
  }, [messages, model, toast])

  return {
    copyMessageContent,
    copyMessageMetadata,
    exportMessageContent,
    exportMessageMetadata,
    copyChatResponses,
    copyChatMetadata,
    exportChatResponses,
    exportChatMetadata,
  }
}
