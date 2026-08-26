import type { Chat, ChatGroup, Message } from '@/components/models/types'
import type { CompletionUsage, ContextCompactedData, DoneMetadata, SternaRouteData } from '@/api/llm'
import { getUserFriendlyErrorMessage } from '@/utils/errorMessages'
import type { StreamCallbacksContext } from './context'

/**
 * Builds the remaining stream callbacks that don't accumulate visible message
 * content: preview/context-compaction notifications, routing and usage/generation
 * bookkeeping, and the terminal onDone / onError handlers.
 */
export function buildLifecycleCallbacks(ctx: StreamCallbacksContext) {
  const { acc, setChatGroups, activeGroupId, chatId, model, toast } = ctx

  return {
  onPreviewStarted: (data: { port: number; command: string; pid: number }) => {
    window.dispatchEvent(new CustomEvent('preview:started', { detail: data }))
  },

  onContextCompacted: (data: ContextCompactedData) => {
    // Handle context compaction notification - show subtle toast
    const tokensSavedK = Math.round(data.tokens_saved / 1000)
    toast({
      title: 'Context optimized',
      description: `Summarized ${data.original_messages - data.compacted_messages} messages to continue seamlessly (saved ~${tokensSavedK}k tokens)`,
      duration: 4000,
    })
  },

  onSternaRoute: (data: SternaRouteData) => {
    acc.sternaRouteData = data
  },

  onGenerationId: (id: string) => {
    acc.generationId = id
  },

  onUsageUpdate: (data: { usage: CompletionUsage; cost: number; prompt_cost: number; completion_cost: number; generation_id?: string; generation_ids?: string[] }) => {
    acc.lastUsageUpdate = data
    if (data.generation_id) acc.generationId = data.generation_id
    if (data.generation_ids) acc.generationIds = data.generation_ids
  },

  onDone: (metadata: DoneMetadata) => {
    // Capture metadata for final update (only used for final done event)
    acc.messageMetadata = metadata
    if (metadata.generation_id) acc.generationId = metadata.generation_id
    if (metadata.generation_ids) acc.generationIds = metadata.generation_ids
  },

  onError: (error: string, detail?: string, code?: string) => {
    console.error('[sendToModel] Stream error:', error, detail, code)

    // Actionable errors (no_api_key, invalid_api_key, insufficient_credits)
    // arrive with a backend-authored message + machine code — keep the
    // message verbatim so it matches the resolution actions we render.
    const rawError = error || detail || ''
    const errorMessage = code
      ? (error || 'An error occurred while processing the response.')
      : (getUserFriendlyErrorMessage(rawError) || 'An error occurred while processing the response. Please try again.')

    // Update chat to show error state
    setChatGroups(prevGroups =>
      prevGroups.map((group: ChatGroup) => {
        if (group.id !== activeGroupId) return group

        return {
          ...group,
          chats: group.chats.map((c: Chat) => {
            if (c.id !== chatId) return c

            // Check if streaming message exists
            const hasStreamingMessage = c.messages.some((m: Message) =>
              m.role === 'assistant' && m.timestamp === acc.streamingMessageTimestamp
            )

            if (hasStreamingMessage) {
              // Update existing streaming message with error
              return {
                ...c,
                messages: c.messages.map((m: Message) => {
                  if (m.timestamp !== acc.streamingMessageTimestamp) return m

                  // Mark message as failed with error
                  return {
                    ...m,
                    error: errorMessage,
                    errorCode: code,
                    isError: true,  // Important: marks stream as complete
                    is_interrupted: true
                  }
                }),
                isLoading: false
              }
            } else {
              // Create new error message (error occurred before any content
              // was streamed). Content carries the friendly message so the
              // message is visible — MessageList filters out isError
              // messages with empty content.
              const errorAssistantMessage: Message = {
                role: 'assistant',
                content: errorMessage,
                timestamp: acc.streamingMessageTimestamp,
                model: model.name,
                model_id: model.model_id,
                provider: model.provider,
                provider_icon_slug: model.provider_icon_slug,
                provider_icon_url: model.provider_icon_url,
                model_icon_slug: model.model_icon_slug,
                model_icon_url: model.model_icon_url,
                error: errorMessage,
                errorCode: code,
                isError: true,  // Important: marks stream as complete
                is_interrupted: true
              }
              return {
                ...c,
                messages: [...c.messages, errorAssistantMessage],
                isLoading: false
              }
            }
          })
        }
      })
    )
  },
  }
}
