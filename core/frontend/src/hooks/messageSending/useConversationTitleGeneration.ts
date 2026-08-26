import { useCallback } from 'react'
import type { ChatGroup, Model } from '@/components/models/types'
import { llmApi } from '@/api/llm'
import { useActiveConversationStore } from '@/store/activeConversationStore'
import type { SetChatGroups } from './types'

export interface UseConversationTitleGenerationProps {
  activeGroupId: string
  setChatGroups: SetChatGroups
}

/**
 * Generates a short conversation title from the first user message, streaming
 * the title into the sidebar in real time via activeConversationStore and then
 * committing it onto the conversation once the stream completes.
 */
export function useConversationTitleGeneration({ activeGroupId, setChatGroups }: UseConversationTitleGenerationProps) {
  return useCallback(async (userMessage: string, model: Model) => {
    // Get store actions for streaming title updates
    const { startGeneratingTitle, updateGeneratingTitle, finishGeneratingTitle, triggerRefresh } = useActiveConversationStore.getState()

    try {
      const prompt = `Generate a short, concise title (3-6 words max) for a conversation that starts with this message. Return ONLY the title, no quotes, no explanation, no punctuation at the end.

User message: "${userMessage.slice(0, 500)}"`

      let title = ''

      // Start streaming title generation (for real-time sidebar updates)
      // This also adds a temporary newConversation to the store for immediate display
      startGeneratingTitle(activeGroupId, 'New Conversation')

      await llmApi.completeStream({
        model: model.model_id,
        messages: [{ role: 'user', content: prompt }],
        temperature: 0.3,
        max_tokens: 30,
        stream: true,
      }, {
        onContent: (content: string) => {
          title += content
          // Clean as we go for display (remove quotes, etc.)
          const cleanedTitle = title.trim().replace(/^["']|["']$/g, '').replace(/\.$/, '').trim()
          // Update the store for real-time sidebar display
          updateGeneratingTitle(cleanedTitle)
        },
        onDone: () => {},
        onError: (error: string) => {
          console.error('[generateConversationTitle] Error:', error)
        },
      })

      // Clean up the title (remove quotes, trim, etc.)
      title = title.trim().replace(/^["']|["']$/g, '').replace(/\.$/, '').trim()

      if (title && title.length > 0 && title.length < 100) {
        // Update the conversation name in the chat groups
        setChatGroups(prevGroups =>
          prevGroups.map((group: ChatGroup) => {
            if (group.id !== activeGroupId) return group
            // Only update if not already custom named
            if (group.isCustomName) return group
            return {
              ...group,
              name: title,
              updatedAt: new Date(),
            }
          })
        )

        // Finish streaming with the final title (keeps it in store until localStorage updates)
        finishGeneratingTitle(title)
      } else {
        // No valid title, just finish
        finishGeneratingTitle()
      }

      // Trigger refresh to update sidebar (will use newConversation from store until localStorage catches up)
      triggerRefresh()
    } catch (error) {
      console.error('[generateConversationTitle] Failed:', error)
      // Make sure to finish even on error
      finishGeneratingTitle()
      triggerRefresh()
      // Silently fail - title generation is not critical
    }
  }, [activeGroupId, setChatGroups])
}
