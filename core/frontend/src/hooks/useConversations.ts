/**
 * useConversations Hook
 *
 * A compatibility hook that provides the same interface as useConversationsSync
 * but uses the new conversationStore backed by PostgreSQL.
 *
 * This allows minimal changes to existing components while switching to
 * the database-backed conversation storage.
 */

import { useEffect, useCallback, useRef, useState } from 'react'
import { useConversationStore, type ConversationSummary, type Conversation } from '@/store/conversationStore'
import type { ChatGroup, Chat, Attachment } from '@/components/models/types'
import { useAuthStore } from '@/store/authStore'
import { fsAPI } from '@/api/fs'
import { getUserId } from '@/lib/userScopedStorage'
import { cacheDelete } from '@/utils/attachmentCache'
import { useToast } from './use-toast'

interface UseConversationsResult {
  /**
   * All chat groups (conversations)
   */
  chatGroups: ChatGroup[]

  /**
   * Set chat groups - triggers save to backend
   */
  setChatGroups: React.Dispatch<React.SetStateAction<ChatGroup[]>>

  /**
   * Loading state
   */
  isLoading: boolean

  /**
   * Error state
   */
  error: string | null

  /**
   * Refresh conversations from backend
   */
  refresh: () => Promise<void>

  /**
   * Create a new conversation in the database
   * Returns the created ChatGroup
   */
  createConversation: (initialChats?: Chat[]) => Promise<ChatGroup>

  /**
   * Load a specific conversation with full chat/message data
   * Returns the loaded ChatGroup or null if not found
   */
  loadConversation: (conversationId: string) => Promise<ChatGroup | null>

  /**
   * Delete a conversation from the database
   * Optionally delete associated workspace files
   */
  deleteConversation: (conversationId: string, deleteWorkspace?: boolean) => Promise<void>

  /**
   * Rename a conversation
   */
  renameConversation: (conversationId: string, newName: string) => Promise<void>

  /**
   * Clear all messages in a conversation's chats
   * Optionally delete associated workspace files
   */
  clearConversation: (conversationId: string, deleteWorkspace?: boolean) => Promise<void>
}

/**
 * Convert ConversationSummary to ChatGroup format for compatibility
 */
function toChatsGroupSummary(summary: ConversationSummary): ChatGroup {
  return {
    id: summary.id,
    name: summary.name,
    createdAt: summary.createdAt,
    updatedAt: summary.updatedAt,
    isCustomName: summary.isCustomName,
    // Note: chats array is empty in summary - full data loaded on demand
    chats: [],
  }
}

/**
 * Convert full Conversation to ChatGroup format
 */
function toChatsGroup(conversation: Conversation): ChatGroup {
  return {
    id: conversation.id,
    name: conversation.name,
    createdAt: conversation.createdAt,
    updatedAt: conversation.updatedAt,
    isCustomName: conversation.isCustomName,
    consigliereSessionId: conversation.consigliereSessionId,
    chats: conversation.chats,
  }
}

/**
 * Helper: Delete all attachments from a conversation's messages
 */
async function deleteConversationAttachments(group: ChatGroup): Promise<void> {
  const attachmentIds = new Set<string>()

  // Collect all attachment IDs from all messages in all chats
  for (const chat of group.chats) {
    for (const message of chat.messages) {
      if (message.attachments) {
        for (const attachment of message.attachments as Attachment[]) {
          if (attachment.id) {
            attachmentIds.add(attachment.id)
          }
        }
      }
    }
  }

  // Delete each attachment from IndexedDB cache
  const deletePromises = Array.from(attachmentIds).map(id =>
    cacheDelete(id).catch(err => {
      console.warn(`[useConversations] Failed to delete attachment ${id}:`, err)
    })
  )

  await Promise.all(deletePromises)

  if (attachmentIds.size > 0) {
    
  }
}

/**
 * Hook for managing conversations with database storage
 *
 * Provides compatibility interface for existing components while
 * using the new conversationStore.
 */
export function useConversations(): UseConversationsResult {
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated)

  // Store state - use selectors to prevent unnecessary re-renders
  const conversations = useConversationStore((state) => state.conversations)
  const activeConversation = useConversationStore((state) => state.activeConversation)
  const storeIsLoading = useConversationStore((state) => state.isLoading)
  const error = useConversationStore((state) => state.error)

  // Store actions
  const fetchConversations = useConversationStore((state) => state.fetchConversations)
  const updateConversation = useConversationStore((state) => state.updateConversation)
  const storeDeleteConversation = useConversationStore((state) => state.deleteConversation)
  const storeRenameConversation = useConversationStore((state) => state.renameConversation)
  const storeClearMessages = useConversationStore((state) => state.clearMessages)
  const storeCreateConversation = useConversationStore((state) => state.createConversation)
  const storeAddChat = useConversationStore((state) => state.addChat)
  const fetchConversation = useConversationStore((state) => state.fetchConversation)

  // Toast for notifications
  const { toast } = useToast()

  // Local state to hold the chat groups
  const [chatGroups, setChatGroupsLocal] = useState<ChatGroup[]>([])
  const [isLoading, setIsLoading] = useState(true)

  // Track if we've loaded
  const hasLoadedRef = useRef(false)

  // Load conversations on mount
  useEffect(() => {
    if (isAuthenticated && !hasLoadedRef.current) {
      hasLoadedRef.current = true
      setIsLoading(true)
      fetchConversations().finally(() => {
        setIsLoading(false)
      })
    }
  }, [isAuthenticated, fetchConversations])

  // Track the last activeConversation ID to detect actual conversation changes
  // This prevents overwriting local state when only message counts change
  const lastActiveConversationIdRef = useRef<string | null>(null)

  // Track if we have pending local changes that shouldn't be overwritten by store sync
  const hasPendingLocalChangesRef = useRef(false)

  // Ref to track current chatGroups for setChatGroups callback
  const chatGroupsRef = useRef<ChatGroup[]>([])

  // Update local chatGroups when store changes
  // IMPORTANT: This must NOT overwrite locally-added messages that haven't been persisted yet
  useEffect(() => {
    // If we have pending local changes, don't overwrite them with store data
    if (hasPendingLocalChangesRef.current) {
      
      return
    }

    

    const groups = conversations.map(toChatsGroupSummary)

    // Replace the active group with full data if available
    if (activeConversation) {
      const idx = groups.findIndex(g => g.id === activeConversation.id)
      if (idx >= 0) {
        // Check if this is the SAME conversation we already have loaded
        // If so, preserve local message changes by only updating if the conversation ID changed
        const isNewConversation = lastActiveConversationIdRef.current !== activeConversation.id
        lastActiveConversationIdRef.current = activeConversation.id

        if (isNewConversation) {
          // New conversation loaded - use store data
          groups[idx] = toChatsGroup(activeConversation)
        } else {
          // Same conversation - check if local state has messages to preserve
          const currentGroup = chatGroupsRef.current.find(g => g.id === activeConversation.id)
          const hasLocalMessages = currentGroup?.chats.some(c => c.messages.length > 0)
          if (currentGroup && hasLocalMessages) {
            // Keep the local group data with its messages
            groups[idx] = currentGroup
          } else {
            groups[idx] = toChatsGroup(activeConversation)
          }
        }
      }
    }

    

    setChatGroupsLocal(groups)
    chatGroupsRef.current = groups
  }, [conversations, activeConversation])

  // Timeout ref for clearing pending local changes flag
  const pendingChangesTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // SetChatGroups - handles updates by syncing to backend
  // IMPORTANT: Must update ref immediately so rapid successive calls get the latest state
  const setChatGroups = useCallback((
    updater: ChatGroup[] | ((prev: ChatGroup[]) => ChatGroup[])
  ) => {
    const currentGroups = chatGroupsRef.current
    const newGroups = typeof updater === 'function' ? updater(currentGroups) : updater

    // Mark that we have pending local changes - prevent store sync from overwriting
    hasPendingLocalChangesRef.current = true

    // Clear any existing timeout
    if (pendingChangesTimeoutRef.current) {
      clearTimeout(pendingChangesTimeoutRef.current)
    }

    // Clear the pending flag after a delay (allows persistence to complete)
    // This ensures we eventually accept store updates even if persistence fails
    pendingChangesTimeoutRef.current = setTimeout(() => {
      hasPendingLocalChangesRef.current = false
    }, 10000) // 10 second timeout

    // Update ref IMMEDIATELY so subsequent calls see the latest state
    // This is critical for rapid calls like: add user message -> set loading state
    // Without this, both calls would use the old state and the second would overwrite the first
    chatGroupsRef.current = newGroups

    // Update local state for optimistic UI
    setChatGroupsLocal(newGroups)

    

    // Find what changed and sync to backend
    for (const newGroup of newGroups) {
      const oldGroup = currentGroups.find(g => g.id === newGroup.id)

      if (!oldGroup) {
        // New group created - already handled by createConversation
        continue
      }

      // Check if name or metadata changed
      if (
        oldGroup.name !== newGroup.name ||
        oldGroup.isCustomName !== newGroup.isCustomName
      ) {
        updateConversation(newGroup.id, {
          name: newGroup.name,
          isCustomName: newGroup.isCustomName,
        }).catch(console.error)
      }
    }

    // Handle deletions
    for (const oldGroup of currentGroups) {
      const stillExists = newGroups.find(g => g.id === oldGroup.id)
      if (!stillExists) {
        storeDeleteConversation(oldGroup.id).catch(console.error)
      }
    }
  }, [updateConversation, storeDeleteConversation])

  const refresh = useCallback(async () => {
    setIsLoading(true)
    await fetchConversations()
    setIsLoading(false)
  }, [fetchConversations])

  /**
   * Create a new conversation with optional initial chats
   * This properly persists to the database and updates the store
   */
  const createConversation = useCallback(async (initialChats?: Chat[]): Promise<ChatGroup> => {
    // Create the conversation in the database
    // storeCreateConversation already updates the store's conversations list and activeConversation
    const conversation = await storeCreateConversation({
      name: 'New Conversation',
      is_custom_name: false,
    })

    // Add initial chats if provided
    if (initialChats && initialChats.length > 0) {
      for (const chat of initialChats) {
        await storeAddChat(
          conversation.id,
          chat.model,
          chat.parameters,
          chat.instructions
        )
      }

      // Refetch to get the chats we just added
      const fullConversation = await fetchConversation(conversation.id)
      if (fullConversation) {
        const newGroup = toChatsGroup(fullConversation)

        // Mark pending changes to prevent sync effect from overwriting with summaries
        hasPendingLocalChangesRef.current = true
        if (pendingChangesTimeoutRef.current) {
          clearTimeout(pendingChangesTimeoutRef.current)
        }
        pendingChangesTimeoutRef.current = setTimeout(() => {
          hasPendingLocalChangesRef.current = false
        }, 5000)

        // Immediately update local state to avoid timing issues with store sync
        // This ensures chatGroups has the new conversation right away
        const updatedGroups = [newGroup, ...chatGroupsRef.current.filter(g => g.id !== newGroup.id)]
        chatGroupsRef.current = updatedGroups
        setChatGroupsLocal(updatedGroups)

        return newGroup
      }
    }

    // Return the conversation from the store (already has full data)
    const newGroup = toChatsGroup(conversation)

    // Mark pending changes to prevent sync effect from overwriting with summaries
    hasPendingLocalChangesRef.current = true
    if (pendingChangesTimeoutRef.current) {
      clearTimeout(pendingChangesTimeoutRef.current)
    }
    pendingChangesTimeoutRef.current = setTimeout(() => {
      hasPendingLocalChangesRef.current = false
    }, 5000)

    // Immediately update local state
    const updatedGroups = [newGroup, ...chatGroupsRef.current.filter(g => g.id !== newGroup.id)]
    chatGroupsRef.current = updatedGroups
    setChatGroupsLocal(updatedGroups)

    return newGroup
  }, [storeCreateConversation, storeAddChat, fetchConversation])

  /**
   * Load a specific conversation with full chat/message data
   * This fetches from the backend and updates the store's activeConversation
   */
  const loadConversation = useCallback(async (conversationId: string): Promise<ChatGroup | null> => {
    try {
      

      const conversation = await fetchConversation(conversationId)
      if (!conversation) {
        console.warn('[useConversations] fetchConversation returned null')
        return null
      }

      

      // Convert to ChatGroup format
      const loadedGroup = toChatsGroup(conversation)

      // Mark pending changes to prevent sync effect from overwriting with summaries
      hasPendingLocalChangesRef.current = true
      if (pendingChangesTimeoutRef.current) {
        clearTimeout(pendingChangesTimeoutRef.current)
      }
      pendingChangesTimeoutRef.current = setTimeout(() => {
        hasPendingLocalChangesRef.current = false
      }, 5000)

      // Immediately update local state to avoid timing issues with store sync
      // Check if conversation exists in local state - if not, add it (happens with paginated conversations)
      const existingGroup = chatGroupsRef.current.find(g => g.id === conversationId)
      let updatedGroups: ChatGroup[]
      if (existingGroup) {
        // Merge local messages with server data to preserve optimistic updates (user messages)
        // This prevents locally-added messages from being wiped out by server fetch
        updatedGroups = chatGroupsRef.current.map(g => {
          if (g.id !== conversationId) return g

          // Merge each chat's messages
          const mergedChats = loadedGroup.chats.map(serverChat => {
            const localChat = existingGroup.chats.find(c => c.id === serverChat.id)
            if (!localChat) return serverChat

            // Find local messages that aren't in server data yet (optimistic updates)
            // These are messages added locally that haven't been persisted/fetched yet
            const serverMessageTimestamps = new Set(
              serverChat.messages.map(m => m.timestamp.getTime())
            )
            const localOnlyMessages = localChat.messages.filter(
              m => !serverMessageTimestamps.has(m.timestamp.getTime())
            )

            // If there are local-only messages, preserve them by appending to server messages
            // Also preserve loading state and other chat properties from local state
            if (localOnlyMessages.length > 0 || localChat.isLoading) {
              return {
                ...serverChat,
                messages: [...serverChat.messages, ...localOnlyMessages],
                isLoading: localChat.isLoading,
              }
            }

            return serverChat
          })

          return { ...loadedGroup, chats: mergedChats }
        })
      } else {
        // Conversation not in local state (loaded via pagination) - add it
        updatedGroups = [loadedGroup, ...chatGroupsRef.current]
      }



      chatGroupsRef.current = updatedGroups
      setChatGroupsLocal(updatedGroups)

      return loadedGroup
    } catch (error) {
      console.error('[useConversations] Failed to load conversation:', error)
      return null
    }
  }, [fetchConversation])

  /**
   * Delete a conversation with optional workspace cleanup
   */
  const deleteConversation = useCallback(async (conversationId: string, deleteWorkspace?: boolean) => {
    // Find the conversation for cleanup
    const groupToDelete = chatGroupsRef.current.find(g => g.id === conversationId)

    // Delete workspace if requested
    if (deleteWorkspace) {
      try {
        const userId = getUserId()
        if (userId) {
          await fsAPI.deleteWorkspace({
            user_id: userId,
            conversation_id: conversationId,
            scope: 'conversation'
          })
        }
      } catch (error) {
        console.error('[useConversations] Failed to delete workspace:', error)
        // Don't block conversation deletion if workspace deletion fails
      }
    }

    // Delete attachments from IndexedDB cache
    if (groupToDelete) {
      try {
        await deleteConversationAttachments(groupToDelete)
      } catch (error) {
        console.error('[useConversations] Failed to delete attachments:', error)
        // Don't block conversation deletion if attachment cleanup fails
      }
    }

    // Delete from backend
    await storeDeleteConversation(conversationId)

    // Update local state
    const updatedGroups = chatGroupsRef.current.filter(g => g.id !== conversationId)
    chatGroupsRef.current = updatedGroups
    setChatGroupsLocal(updatedGroups)

    toast({
      title: 'Conversation Deleted',
      description: deleteWorkspace ? 'Conversation and workspace deleted' : 'The conversation has been removed',
    })
  }, [storeDeleteConversation, toast])

  /**
   * Rename a conversation
   */
  const renameConversation = useCallback(async (conversationId: string, newName: string) => {
    await storeRenameConversation(conversationId, newName)

    // Update local state
    const updatedGroups = chatGroupsRef.current.map(g =>
      g.id === conversationId
        ? { ...g, name: newName, isCustomName: true, updatedAt: new Date() }
        : g
    )
    chatGroupsRef.current = updatedGroups
    setChatGroupsLocal(updatedGroups)

    toast({
      title: 'Conversation Renamed',
      description: `Renamed to "${newName}"`,
    })
  }, [storeRenameConversation, toast])

  /**
   * Clear all messages in a conversation with optional workspace cleanup
   */
  const clearConversation = useCallback(async (conversationId: string, deleteWorkspace?: boolean) => {
    // Find the conversation for cleanup
    const groupToClear = chatGroupsRef.current.find(g => g.id === conversationId)

    // Delete workspace if requested
    if (deleteWorkspace) {
      try {
        const userId = getUserId()
        if (userId) {
          await fsAPI.deleteWorkspace({
            user_id: userId,
            conversation_id: conversationId,
            scope: 'conversation'
          })
        }
      } catch (error) {
        console.error('[useConversations] Failed to delete workspace:', error)
        // Don't block message clearing if workspace deletion fails
      }
    }

    // Delete attachments from IndexedDB cache
    if (groupToClear) {
      try {
        await deleteConversationAttachments(groupToClear)
      } catch (error) {
        console.error('[useConversations] Failed to delete attachments:', error)
        // Don't block message clearing if attachment cleanup fails
      }
    }

    // Clear messages from backend for each chat
    if (groupToClear) {
      for (const chat of groupToClear.chats) {
        await storeClearMessages(conversationId, chat.id)
      }
    }

    // Update local state - clear messages from all chats
    const updatedGroups = chatGroupsRef.current.map(g => {
      if (g.id === conversationId) {
        return {
          ...g,
          chats: g.chats.map(chat => ({ ...chat, messages: [] })),
          updatedAt: new Date(),
        }
      }
      return g
    })
    chatGroupsRef.current = updatedGroups
    setChatGroupsLocal(updatedGroups)

    toast({
      title: 'Conversation Cleared',
      description: deleteWorkspace ? 'All messages and workspace removed' : 'All messages have been removed',
    })
  }, [storeClearMessages, toast])

  return {
    chatGroups,
    setChatGroups,
    isLoading: isLoading || storeIsLoading,
    error,
    refresh,
    createConversation,
    loadConversation,
    deleteConversation,
    renameConversation,
    clearConversation,
  }
}
