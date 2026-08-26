/**
 * Copy/export/save actions for ModelComparisonPage: whole-conversation and
 * per-chat clipboard copy, file export, "save to knowledge base", opening
 * Consigliere, and clearing all messages. Grouped together because every
 * one of them is a side-effecting action keyed off the active group/chats
 * that ends in a toast, not a piece of derived render state.
 */
import { useCallback } from 'react'
import { conversationsAPI } from '@/api/conversations'
import { hasErrorResponse } from '@/utils/errorMessages'
import { buildConversationResponsesText, buildConversationMetadata, buildChatResponsesText, buildChatMetadata, generateFilename } from '@/utils/chatUtils'
import type { useToast } from '@/hooks/use-toast'
import type { Chat, ChatGroup, Model } from '../types'

interface UseConversationActionsParams {
  chats: Chat[]
  activeGroup: ChatGroup | undefined
  activeGroupId: string
  currentModel: Model | null
  openConsigliere: (chatGroup?: ChatGroup, currentModel?: string) => Promise<string | null>
  setChatGroups: (updater: (prevGroups: ChatGroup[]) => ChatGroup[]) => void
  toast: ReturnType<typeof useToast>['toast']
  setSharedInput: (value: string) => void
  setEstimatedCosts: (costs: null) => void
  isSavingToKnowledgeBase: boolean
  setIsSavingToKnowledgeBase: (value: boolean) => void
  savingChatId: string | null
  setSavingChatId: (chatId: string | null) => void
}

export function useConversationActions({
  chats,
  activeGroup,
  activeGroupId,
  currentModel,
  openConsigliere,
  setChatGroups,
  toast,
  setSharedInput,
  setEstimatedCosts,
  isSavingToKnowledgeBase,
  setIsSavingToKnowledgeBase,
  savingChatId,
  setSavingChatId,
}: UseConversationActionsParams) {
  const copyConversationResponses = () => {
    const text = buildConversationResponsesText(chats)
    navigator.clipboard.writeText(text)
    toast({ title: 'Copied', description: 'All responses copied to clipboard' })
  }

  const copyConversationMetadata = () => {
    const data = buildConversationMetadata(chats, false)
    navigator.clipboard.writeText(JSON.stringify(data, null, 2))
    toast({ title: 'Copied', description: 'All metadata copied to clipboard' })
  }

  const exportConversationResponses = () => {
    const text = buildConversationResponsesText(chats)
    const blob = new Blob([text], { type: 'text/plain' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = generateFilename('conversation', 'txt')
    a.click()
    URL.revokeObjectURL(url)
    toast({ title: 'Exported', description: 'All responses exported' })
  }

  const exportConversationMetadata = () => {
    const data = buildConversationMetadata(chats, false)
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = generateFilename('conversation-metadata', 'json')
    a.click()
    URL.revokeObjectURL(url)
    toast({ title: 'Exported', description: 'All metadata exported' })
  }

  // Save conversation to knowledge base (for all views)
  const handleSaveToKnowledgeBase = useCallback(async () => {
    if (isSavingToKnowledgeBase || !activeGroupId) return

    setIsSavingToKnowledgeBase(true)
    try {
      const result = await conversationsAPI.saveToKnowledgeBase(activeGroupId)
      toast({ title: 'Saved', description: `Saved to knowledge base: ${result.filename}` })
    } catch (error) {
      const errorData = hasErrorResponse(error)
        ? error.response?.data as { existing_document_id?: string; error?: string } | undefined
        : undefined
      if (errorData?.existing_document_id) {
        toast({ title: 'Already saved', description: errorData.error || 'This conversation is already in your knowledge base', variant: 'destructive' })
      } else if (errorData?.error) {
        toast({ title: 'Failed to save', description: errorData.error, variant: 'destructive' })
      } else {
        toast({ title: 'Error', description: 'Failed to save to knowledge base', variant: 'destructive' })
      }
    } finally {
      setIsSavingToKnowledgeBase(false)
    }
  }, [activeGroupId, isSavingToKnowledgeBase, toast, setIsSavingToKnowledgeBase])

  // Save single chat to knowledge base
  const handleSaveChatToKnowledgeBase = useCallback(async (chatId: string) => {
    if (savingChatId || !activeGroupId) return

    const chat = chats.find(c => c.id === chatId)
    if (!chat) return

    setSavingChatId(chatId)
    try {
      // Currently saves entire conversation - in future could be chat-specific
      const result = await conversationsAPI.saveToKnowledgeBase(activeGroupId)
      const modelName = chat.model?.name || 'Chat'
      toast({ title: 'Saved', description: `${modelName} saved to knowledge base: ${result.filename}` })
    } catch (error) {
      const errorData = hasErrorResponse(error)
        ? error.response?.data as { existing_document_id?: string; error?: string } | undefined
        : undefined
      if (errorData?.existing_document_id) {
        toast({ title: 'Already saved', description: errorData.error || 'This conversation is already in your knowledge base', variant: 'destructive' })
      } else if (errorData?.error) {
        toast({ title: 'Failed to save', description: errorData.error, variant: 'destructive' })
      } else {
        toast({ title: 'Error', description: 'Failed to save to knowledge base', variant: 'destructive' })
      }
    } finally {
      setSavingChatId(null)
    }
  }, [activeGroupId, chats, savingChatId, toast, setSavingChatId])

  // Per-chat copy/export functions (for immersive mode options menu)
  const copyChatResponses = (chatId: string) => {
    const chat = chats.find(c => c.id === chatId)
    if (!chat) return
    const text = buildChatResponsesText(chat.messages)
    navigator.clipboard.writeText(text)
    toast({ title: 'Copied', description: 'Responses copied to clipboard' })
  }

  const copyChatMetadata = (chatId: string) => {
    const chat = chats.find(c => c.id === chatId)
    if (!chat) return
    const data = buildChatMetadata(chat.messages)
    navigator.clipboard.writeText(JSON.stringify(data, null, 2))
    toast({ title: 'Copied', description: 'Metadata copied to clipboard' })
  }

  const exportChatResponses = (chatId: string) => {
    const chat = chats.find(c => c.id === chatId)
    if (!chat) return
    const text = buildChatResponsesText(chat.messages)
    const modelName = chat.model?.name?.replace(/[^a-z0-9]/gi, '-') || 'chat'
    const blob = new Blob([text], { type: 'text/plain' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = generateFilename(modelName, 'txt')
    a.click()
    URL.revokeObjectURL(url)
    toast({ title: 'Exported', description: 'Responses exported' })
  }

  const exportChatMetadata = (chatId: string) => {
    const chat = chats.find(c => c.id === chatId)
    if (!chat) return
    const data = buildChatMetadata(chat.messages)
    const modelName = chat.model?.name?.replace(/[^a-z0-9]/gi, '-') || 'chat'
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = generateFilename(`${modelName}-metadata`, 'json')
    a.click()
    URL.revokeObjectURL(url)
    toast({ title: 'Exported', description: 'Metadata exported' })
  }

  const handleOpenConsigliere = async () => {
    if (activeGroup && currentModel) {
      const sessionId = await openConsigliere(activeGroup, currentModel.model_id)
      if (sessionId && sessionId !== activeGroup.consigliereSessionId) {
        setChatGroups(prevGroups =>
          prevGroups.map(group =>
            group.id === activeGroupId
              ? { ...group, consigliereSessionId: sessionId }
              : group
          )
        )
      }
    } else {
      toast({
        title: "Cannot open Consigliere",
        description: "Please select a model first",
        variant: "destructive"
      })
    }
  }

  const clearConversations = () => {
    // Clear messages and Consigliere session in a single state update to avoid race conditions
    setChatGroups(prevGroups =>
      prevGroups.map(group => {
        if (group.id !== activeGroupId) return group

        // Clear messages from all chats
        const clearedChats = group.chats.map(chat => ({
          ...chat,
          messages: []
        }))

        return {
          ...group,
          chats: clearedChats,
          consigliereSessionId: undefined,
          updatedAt: new Date(),
          name: 'New Conversation',
          isCustomName: false  // Allow LLM to generate name after next message
        }
      })
    )

    setSharedInput('')
    setEstimatedCosts(null)
    toast({
      title: 'Cleared',
      description: 'All conversations have been cleared'
    })
  }

  return {
    copyConversationResponses,
    copyConversationMetadata,
    exportConversationResponses,
    exportConversationMetadata,
    handleSaveToKnowledgeBase,
    handleSaveChatToKnowledgeBase,
    copyChatResponses,
    copyChatMetadata,
    exportChatResponses,
    exportChatMetadata,
    handleOpenConsigliere,
    clearConversations,
  }
}
