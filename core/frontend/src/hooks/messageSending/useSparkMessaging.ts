import { useCallback } from 'react'
import type { Chat, ChatGroup, Model, Message } from '@/components/models/types'
import { sparksAPI } from '@/api/sparks'
import type { SetChatGroups } from './types'
import type { SendToModelOptions } from './requestPayload'

export interface UseSparkMessagingProps {
  chats: Chat[]
  activeGroupId: string
  setChatGroups: SetChatGroups
  sendToModel: (chatId: string, model: Model, messages: Message[], options?: SendToModelOptions) => Promise<void>
}

export interface UseSparkMessagingReturn {
  sendSparkFixMessage: (chatId: string, content: string, sparkFixRequest: { spark_id: string; spark_title: string; error: string }) => Promise<void>
  sendIgniteMessage: (chatId: string, sparkIgniteRequest: { spark_id: string; spark_title: string }) => Promise<void>
}

/**
 * The two spark-specific message flows: asking a model to fix a broken
 * spark, and igniting a spark into a full Next.js project. Both post a
 * synthetic user message, then delegate the actual model call to sendToModel
 * with spark-specific request metadata and parameter overrides.
 */
export function useSparkMessaging({
  chats,
  activeGroupId,
  setChatGroups,
  sendToModel,
}: UseSparkMessagingProps): UseSparkMessagingReturn {
  // Send a spark fix message with spark_fix_request metadata
  const sendSparkFixMessage = useCallback(async (
    chatId: string,
    content: string,
    sparkFixRequest: { spark_id: string; spark_title: string; error: string }
  ) => {
    const chat = chats.find(c => c.id === chatId)
    if (!chat?.model) return

    // Create a user message for the fix request
    const userMessage: Message = {
      role: 'user',
      content,
      timestamp: new Date(),
    }

    // Get current messages and add the fix request message
    const messages = [...chat.messages, userMessage]

    // Update UI with the user message first
    setChatGroups(prevGroups =>
      prevGroups.map((group: ChatGroup) =>
        group.id === activeGroupId
          ? {
              ...group,
              chats: group.chats.map((c: Chat) =>
                c.id === chatId
                  ? { ...c, messages }
                  : c
              ),
              updatedAt: new Date(),
            }
          : group
      )
    )

    // Send to model with spark_fix_request metadata and ensure sparks is enabled
    await sendToModel(chatId, chat.model, messages, {
      sparkFixRequest,
      parameterOverrides: { enable_sparks: true }
    })
  }, [chats, activeGroupId, setChatGroups, sendToModel])

  // Send a spark ignite message with spark_ignite_request metadata
  const sendIgniteMessage = useCallback(async (
    chatId: string,
    sparkIgniteRequest: { spark_id: string; spark_title: string }
  ) => {
    const chat = chats.find(c => c.id === chatId)
    if (!chat?.model) return

    const content = `Turn the spark "${sparkIgniteRequest.spark_title}" into a full Next.js project that I can preview and deploy.`
    const userMessage: Message = {
      role: 'user',
      content,
      timestamp: new Date(),
    }

    const messages = [...chat.messages, userMessage]

    // Update UI with the user message first
    setChatGroups(prevGroups =>
      prevGroups.map((group: ChatGroup) =>
        group.id === activeGroupId
          ? {
              ...group,
              chats: group.chats.map((c: Chat) =>
                c.id === chatId
                  ? { ...c, messages }
                  : c
              ),
              updatedAt: new Date(),
            }
          : group
      )
    )

    // Send to model with spark_ignite_request metadata and ensure sparks + file tools are enabled
    await sendToModel(chatId, chat.model, messages, {
      sparkIgniteRequest,
      parameterOverrides: { enable_sparks: true, enable_file_tools: true }
    })

    // After ignite completes, refresh spark data to pick up is_ignited=true
    try {
      const refreshed = await sparksAPI.get(sparkIgniteRequest.spark_id)
      if (refreshed?.is_ignited) {
        setChatGroups((prev) =>
          prev.map((group: ChatGroup) =>
            group.id !== activeGroupId ? group : {
              ...group,
              chats: group.chats.map((c: Chat) => ({
                ...c,
                messages: c.messages.map((m: Message) => ({
                  ...m,
                  sparks: m.sparks?.map((s) =>
                    s.id === sparkIgniteRequest.spark_id ? { ...s, is_ignited: true } : s
                  ),
                })),
              })),
            }
          )
        )
      }
    } catch { /* non-critical — page reload will pick up correct state */ }
  }, [chats, activeGroupId, setChatGroups, sendToModel])

  return { sendSparkFixMessage, sendIgniteMessage }
}
