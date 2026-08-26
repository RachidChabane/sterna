/**
 * useChatManagement Hook
 *
 * Manages chat operations within the active group:
 * - Add/remove chats
 * - Update chat properties (model, messages, parameters, loading state)
 * - Move chats (reorder)
 * - Clear chat messages
 * - Apply settings to all chats
 * - Toggle chat disabled/hidden states
 */

import { useToast } from '@/hooks/use-toast'
import type { Chat, Model, Message, ModelParameters } from '@/components/models/types'
import { MAX_CHATS, DEFAULT_PARAMETERS } from '@/components/models/constants'
import { toModelCatalogEntry } from '@/components/models/modelCatalog'
import useModelStore from '@/store/modelStore'
import { useConversationStore } from '@/store/conversationStore'
import { fsAPI } from '@/api/fs'
import { getUserId } from '@/lib/userScopedStorage'

interface UseChatManagementProps {
  chats: Chat[]
  currentModel: Model | null
  updateActiveGroup: (updater: (prevChats: Chat[]) => Chat[]) => void
  cancelChat: (chatId: string) => void
  conversationId: string
}

interface UseChatManagementReturn {
  // Chat CRUD
  addChat: (position?: number) => Promise<void>
  removeChat: (chatId: string, deleteWorkspace?: boolean) => void
  clearChat: (chatId: string, deleteWorkspace?: boolean) => void

  // Chat updates
  updateChat: (chatId: string, data: Partial<Chat>) => void
  updateChatModel: (chatId: string, model: Model) => void
  updateChatMessages: (chatId: string, messages: Message[]) => void
  updateChatParameters: (chatId: string, parameters: ModelParameters) => void
  updateChatLoading: (chatId: string, isLoading: boolean) => void
  updateChatDisabled: (chatId: string, disabled: boolean) => void
  updateChatHidden: (chatId: string, hidden: boolean) => void

  // Batch operations
  applyParametersToAllChats: (parameters: ModelParameters) => void

  // Reordering
  moveLeft: (chatId: string) => void
  moveRight: (chatId: string) => void
}

export function useChatManagement({
  chats,
  currentModel,
  updateActiveGroup,
  cancelChat,
  conversationId
}: UseChatManagementProps): UseChatManagementReturn {
  const { toast } = useToast()
  const { addRecentChatModel } = useModelStore()
  const storeAddChat = useConversationStore((state) => state.addChat)
  const storeRemoveChat = useConversationStore((state) => state.removeChat)
  const storeUpdateChat = useConversationStore((state) => state.updateChat)

  const addChat = async (position?: number) => {
    if (chats.length >= MAX_CHATS) {
      toast({
        title: 'Maximum chats reached',
        description: `You can have up to ${MAX_CHATS} chats at once`,
        variant: 'destructive'
      })
      return
    }

    try {
      // Determine which model to use for the new chat:
      // 1. If inserting at a position, use the model from the adjacent chat (prefer the one before)
      // 2. If no position or no adjacent chat, use the first chat's model
      // 3. Fall back to app's currentModel if no existing chats
      let modelForNewChat: Model | null = currentModel
      if (chats.length > 0) {
        if (position !== undefined && position > 0 && position <= chats.length) {
          // Use the model from the chat before the insertion point
          modelForNewChat = chats[position - 1]?.model || chats[0]?.model || currentModel
        } else {
          // Use the first chat's model
          modelForNewChat = chats[0]?.model || currentModel
        }
      }

      // Create the chat in the backend first
      const newChat = await storeAddChat(conversationId, modelForNewChat, { ...DEFAULT_PARAMETERS })

      

      // Update local state with the persisted chat
      updateActiveGroup(prevChats => {
        

        // Check if chat already exists (from store sync) to avoid duplicates
        if (prevChats.some(c => c.id === newChat.id)) {
          
          return prevChats
        }

        // If position is specified, insert at that position
        if (position !== undefined && position >= 0 && position <= prevChats.length) {
          const newChats = [...prevChats]
          newChats.splice(position, 0, newChat)
          return newChats
        }
        // Otherwise, add to the end
        return [...prevChats, newChat]
      })

      // Add the model to recent chat models if it exists
      if (modelForNewChat) {
        addRecentChatModel(modelForNewChat.model_id, toModelCatalogEntry(modelForNewChat))
      }

      toast({
        title: 'Chat added',
        description: `New chat created (${chats.length + 1}/${MAX_CHATS})`
      })
    } catch (error) {
      console.error('[useChatManagement] Failed to add chat:', error)
      toast({
        title: 'Failed to add chat',
        description: 'Could not create the chat. Please try again.',
        variant: 'destructive'
      })
    }
  }

  const removeChat = async (chatId: string, deleteWorkspace?: boolean) => {
    if (chats.length <= 1) {
      toast({
        title: 'Cannot remove',
        description: 'You must have at least one chat',
        variant: 'destructive'
      })
      return
    }

    // Find the chat and its position before removing
    const chatIndex = chats.findIndex(c => c.id === chatId)
    const chatToRemove = chats[chatIndex]

    if (!chatToRemove) return

    try {
      // Delete workspace if requested
      if (deleteWorkspace) {
        try {
          const userId = getUserId()
          if (userId) {
            await fsAPI.deleteWorkspace({
              user_id: userId,
              conversation_id: conversationId,
              chat_id: chatId,
              scope: 'chat'
            })
          }
        } catch (error) {
          console.error('Failed to delete workspace:', error)
          // Don't block chat removal if workspace deletion fails
        }
      }

      // Delete from backend first
      await storeRemoveChat(conversationId, chatId)

      // Remove from local state
      updateActiveGroup(prevChats => prevChats.filter(c => c.id !== chatId))

      // Show toast with undo action
      toast({
        title: 'Chat removed',
        description: deleteWorkspace ? 'Chat and workspace deleted' : 'Chat has been closed',
        action: {
          label: 'Undo',
          onClick: async () => {
            try {
              // Re-create the chat in the backend
              const restoredChat = await storeAddChat(
                conversationId,
                chatToRemove.model,
                chatToRemove.parameters
              )

              // Restore to local state at original position
              updateActiveGroup(prevChats => {
                const newChats = [...prevChats]
                // Use restored chat with new ID from backend, but keep original messages
                const chatWithMessages = {
                  ...restoredChat,
                  messages: chatToRemove.messages
                }
                newChats.splice(chatIndex, 0, chatWithMessages)
                return newChats
              })

              toast({
                title: 'Chat restored',
                description: 'The chat has been restored'
              })
            } catch (error) {
              console.error('[useChatManagement] Failed to restore chat:', error)
              toast({
                title: 'Failed to restore',
                description: 'Could not restore the chat',
                variant: 'destructive'
              })
            }
          }
        }
      })
    } catch (error) {
      console.error('[useChatManagement] Failed to remove chat:', error)
      toast({
        title: 'Failed to remove chat',
        description: 'Could not delete the chat. Please try again.',
        variant: 'destructive'
      })
    }
  }

  const clearChat = async (chatId: string, deleteWorkspace?: boolean) => {
    // Abort any in-flight request for this chat
    cancelChat(chatId)

    // Delete workspace if requested
    if (deleteWorkspace) {
      try {
        const userId = getUserId()
        if (userId) {
          await fsAPI.deleteWorkspace({
            user_id: userId,
            conversation_id: conversationId,
            chat_id: chatId,
            scope: 'chat'
          })
        }
      } catch (error) {
        console.error('Failed to delete workspace:', error)
        // Don't block chat clearing if workspace deletion fails
      }
    }

    updateActiveGroup(prevChats => {
      const updatedChats = prevChats.map(c =>
        c.id === chatId ? { ...c, messages: [], isLoading: false } : c
      )
      return updatedChats
    })

    toast({
      title: 'Cleared',
      description: deleteWorkspace ? 'Chat messages and workspace cleared' : 'Chat messages cleared'
    })
  }

  const updateChat = (chatId: string, data: Partial<Chat>) => {
    // Update local state
    updateActiveGroup(prevChats =>
      prevChats.map(c => c.id === chatId ? { ...c, ...data } : c)
    )

    // Persist to backend
    storeUpdateChat(conversationId, chatId, data).catch(error => {
      console.error('[useChatManagement] Failed to persist chat update:', error)
    })
  }

  const updateChatModel = (chatId: string, model: Model) => {
    

    // Track updated parameters for backend persistence
    let updatedParametersForBackend: ModelParameters | null = null
    let updateCount = 0

    // Update local state - calculate parameters inside callback to use latest state
    updateActiveGroup(prevChats => {
      

      return prevChats.map(c => {
        const shouldUpdate = c.id === chatId
        
        if (!shouldUpdate) return c

        updateCount++
        

        // Keep all features enabled regardless of model capabilities
        const updatedParameters = { ...c.parameters }

        // Capture for backend call
        updatedParametersForBackend = updatedParameters

        return { ...c, model, parameters: updatedParameters }
      })
    })

    

    // Persist to backend (use captured parameters)
    if (updatedParametersForBackend) {
      storeUpdateChat(conversationId, chatId, { model, parameters: updatedParametersForBackend }).catch(error => {
        console.error('[useChatManagement] Failed to persist chat model update:', error)
      })
    }

    // Add to recent chat models
    if (model) {
      addRecentChatModel(model.model_id, toModelCatalogEntry(model))
    }
  }

  const updateChatMessages = (chatId: string, messages: Message[]) => {
    updateActiveGroup(prevChats =>
      prevChats.map(c => c.id === chatId ? { ...c, messages } : c)
    )
  }

  const updateChatParameters = (chatId: string, parameters: ModelParameters) => {
    updateActiveGroup(prevChats =>
      prevChats.map(c => c.id === chatId ? { ...c, parameters } : c)
    )

    // Persist to backend
    storeUpdateChat(conversationId, chatId, { parameters }).catch(error => {
      console.error('[useChatManagement] Failed to persist chat parameters update:', error)
    })
  }

  const updateChatLoading = (chatId: string, isLoading: boolean) => {
    updateActiveGroup(prevChats =>
      prevChats.map(c => c.id === chatId ? { ...c, isLoading } : c)
    )
  }

  const updateChatDisabled = (chatId: string, disabled: boolean) => {
    updateActiveGroup(prevChats =>
      prevChats.map(c => c.id === chatId ? { ...c, disabled } : c)
    )

    // Persist to backend
    storeUpdateChat(conversationId, chatId, { disabled }).catch(error => {
      console.error('[useChatManagement] Failed to persist chat disabled update:', error)
    })
  }

  const updateChatHidden = (chatId: string, hidden: boolean) => {
    updateActiveGroup(prevChats =>
      prevChats.map(c => c.id === chatId ? { ...c, hidden } : c)
    )

    // Persist to backend
    storeUpdateChat(conversationId, chatId, { hidden }).catch(error => {
      console.error('[useChatManagement] Failed to persist chat hidden update:', error)
    })
  }

  const applyParametersToAllChats = (parameters: ModelParameters) => {
    updateActiveGroup(prevChats =>
      prevChats.map(chat => ({ ...chat, parameters }))
    )

    // Persist to backend for all chats
    chats.forEach(chat => {
      storeUpdateChat(conversationId, chat.id, { parameters }).catch(error => {
        console.error('[useChatManagement] Failed to persist chat parameters update:', error)
      })
    })

    toast({
      title: 'Settings applied',
      description: 'Applied settings to all chats in this conversation'
    })
  }

  const moveLeft = (chatId: string) => {
    let chatToMove: string | null = null
    let chatToSwap: string | null = null
    let newPositionForMoved: number = 0
    let newPositionForSwapped: number = 0

    updateActiveGroup(prevChats => {
      const currentIndex = prevChats.findIndex(c => c.id === chatId)
      if (currentIndex <= 0) return prevChats // Can't move left if first

      const newChats = [...prevChats]
      const temp = newChats[currentIndex]
      newChats[currentIndex] = newChats[currentIndex - 1]
      newChats[currentIndex - 1] = temp

      // Track which chats need position updates
      chatToMove = chatId
      chatToSwap = newChats[currentIndex].id
      newPositionForMoved = currentIndex - 1
      newPositionForSwapped = currentIndex

      return newChats
    })

    // Persist position changes to backend
    if (chatToMove && chatToSwap) {
      storeUpdateChat(conversationId, chatToMove, { position: newPositionForMoved }).catch(error => {
        console.error('[useChatManagement] Failed to persist chat position:', error)
      })
      storeUpdateChat(conversationId, chatToSwap, { position: newPositionForSwapped }).catch(error => {
        console.error('[useChatManagement] Failed to persist chat position:', error)
      })
    }
  }

  const moveRight = (chatId: string) => {
    let chatToMove: string | null = null
    let chatToSwap: string | null = null
    let newPositionForMoved: number = 0
    let newPositionForSwapped: number = 0

    updateActiveGroup(prevChats => {
      const currentIndex = prevChats.findIndex(c => c.id === chatId)
      if (currentIndex === -1 || currentIndex >= prevChats.length - 1) return prevChats // Can't move right if last

      const newChats = [...prevChats]
      const temp = newChats[currentIndex]
      newChats[currentIndex] = newChats[currentIndex + 1]
      newChats[currentIndex + 1] = temp

      // Track which chats need position updates
      chatToMove = chatId
      chatToSwap = newChats[currentIndex].id
      newPositionForMoved = currentIndex + 1
      newPositionForSwapped = currentIndex

      return newChats
    })

    // Persist position changes to backend
    if (chatToMove && chatToSwap) {
      storeUpdateChat(conversationId, chatToMove, { position: newPositionForMoved }).catch(error => {
        console.error('[useChatManagement] Failed to persist chat position:', error)
      })
      storeUpdateChat(conversationId, chatToSwap, { position: newPositionForSwapped }).catch(error => {
        console.error('[useChatManagement] Failed to persist chat position:', error)
      })
    }
  }

  return {
    addChat,
    removeChat,
    clearChat,
    updateChat,
    updateChatModel,
    updateChatMessages,
    updateChatParameters,
    updateChatLoading,
    updateChatDisabled,
    updateChatHidden,
    applyParametersToAllChats,
    moveLeft,
    moveRight
  }
}
