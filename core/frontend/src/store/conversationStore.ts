/**
 * Conversation Store
 *
 * Zustand store for managing conversations, chats, and messages.
 * Replaces localStorage-based storage with PostgreSQL backend.
 */

import { create } from 'zustand'
import { devtools } from 'zustand/middleware'
import {
  conversationsAPI,
  toFrontendConversation,
  toFrontendChat,
  toFrontendMessage,
  type APIConversation,
  type APIConversationDetail,
  type CreateConversationRequest,
  type CreateMessageRequest,
} from '@/api/conversations'
import type { Chat, Message, ModelParameters, ChatInstructions } from '@/components/models/types'
import type { Model } from '@/api/llm'
import useModelStore from '@/store/modelStore'
import { getDefaultModelParameters } from '@/config/modelParameters'

// ============================================================================
// Types
// ============================================================================

/**
 * Model info for a single chat
 */
interface ChatModelInfo {
  modelId: string
  modelProvider: string | null
}

/**
 * Conversation summary for list views
 */
export interface ConversationSummary {
  id: string
  name: string
  isCustomName: boolean
  isArchived: boolean
  isPinned: boolean
  messageCount: number
  chatCount: number
  modelId: string | null
  modelProvider: string | null
  chatModels: ChatModelInfo[]  // All chat models for hover display
  createdAt: Date
  updatedAt: Date
  lastMessageAt: Date | null
}

/**
 * Full conversation with chats and messages
 */
export interface Conversation {
  id: string
  name: string
  createdAt: Date
  updatedAt: Date
  chats: Chat[]
  isCustomName?: boolean
  consigliereSessionId?: string
  isArchived?: boolean
  isPinned?: boolean
}

interface ConversationState {
  // Data
  conversations: ConversationSummary[]
  activeConversation: Conversation | null
  activeConversationId: string | null

  // Pagination state
  totalCount: number
  currentPage: number
  hasMore: boolean

  // Loading states
  isLoading: boolean
  isLoadingMore: boolean
  isLoadingConversation: boolean
  isSaving: boolean

  // Error state
  error: string | null

  // Title generation state (for streaming titles)
  generatingTitleForId: string | null
  generatingTitleText: string
}

interface ConversationActions {
  // Data fetching
  fetchConversations: () => Promise<void>
  fetchMoreConversations: () => Promise<void>
  fetchConversation: (id: string) => Promise<Conversation | null>

  // Conversation CRUD
  createConversation: (data?: CreateConversationRequest) => Promise<Conversation>
  updateConversation: (id: string, data: Partial<Conversation>) => Promise<void>
  deleteConversation: (id: string) => Promise<void>
  renameConversation: (id: string, name: string) => Promise<void>

  // Conversation actions
  archiveConversation: (id: string) => Promise<void>
  unarchiveConversation: (id: string) => Promise<void>
  pinConversation: (id: string) => Promise<void>
  unpinConversation: (id: string) => Promise<void>

  // Active conversation
  setActiveConversation: (id: string | null) => Promise<void>
  clearActiveConversation: () => void

  // Chat management
  addChat: (conversationId: string, model: Model | null, parameters?: ModelParameters, instructions?: ChatInstructions) => Promise<Chat>
  updateChat: (conversationId: string, chatId: string, data: Partial<Chat> & { position?: number }) => Promise<void>
  removeChat: (conversationId: string, chatId: string) => Promise<void>

  // Message management
  addMessage: (conversationId: string, chatId: string, message: CreateMessageRequest) => Promise<Message>
  addMessagesBulk: (conversationId: string, chatId: string, messages: CreateMessageRequest[]) => Promise<Message[]>
  updateMessage: (conversationId: string, chatId: string, messageId: string, data: Partial<Message>) => Promise<void>
  deleteMessage: (conversationId: string, chatId: string, messageId: string) => Promise<void>
  clearMessages: (conversationId: string, chatId: string) => Promise<void>

  // Local state updates (for optimistic updates)
  updateLocalMessage: (chatId: string, messageId: string, data: Partial<Message>) => void
  appendLocalMessage: (chatId: string, message: Message) => void
  setChatLoading: (chatId: string, isLoading: boolean) => void

  // Title generation
  startGeneratingTitle: (conversationId: string, initialName?: string) => void
  updateGeneratingTitle: (text: string) => void
  finishGeneratingTitle: (finalTitle?: string) => void

  // Utility
  getActiveChat: () => Chat | null
  refreshConversations: () => Promise<void>
}

type ConversationStore = ConversationState & ConversationActions

// ============================================================================
// Store Implementation
// ============================================================================

export const useConversationStore = create<ConversationStore>()(
  devtools(
    (set, get) => ({
      // Initial state
      conversations: [],
      activeConversation: null,
      activeConversationId: null,
      totalCount: 0,
      currentPage: 1,
      hasMore: false,
      isLoading: false,
      isLoadingMore: false,
      isLoadingConversation: false,
      isSaving: false,
      error: null,
      generatingTitleForId: null,
      generatingTitleText: '',

      // -----------------------------------------------------------------------
      // Data Fetching
      // -----------------------------------------------------------------------

      fetchConversations: async () => {
        set({ isLoading: true, error: null })
        try {
          const response = await conversationsAPI.listConversationsPaginated({ page: 1 })
          const conversations = response.results.map(toConversationSummary)
          set({
            conversations,
            totalCount: response.count,
            currentPage: 1,
            hasMore: response.next !== null,
            isLoading: false,
          })
        } catch (error) {
          console.error('Failed to fetch conversations:', error)
          set({ error: 'Failed to load conversations', isLoading: false })
        }
      },

      fetchMoreConversations: async () => {
        const state = get()
        if (state.isLoadingMore || !state.hasMore) return

        set({ isLoadingMore: true, error: null })
        try {
          const nextPage = state.currentPage + 1
          const response = await conversationsAPI.listConversationsPaginated({ page: nextPage })
          const newConversations = response.results.map(toConversationSummary)

          set(s => ({
            conversations: [...s.conversations, ...newConversations],
            currentPage: nextPage,
            hasMore: response.next !== null,
            isLoadingMore: false,
          }))
        } catch (error) {
          console.error('Failed to fetch more conversations:', error)
          set({ error: 'Failed to load more conversations', isLoadingMore: false })
        }
      },

      fetchConversation: async (id: string) => {
        
        set({ isLoadingConversation: true, error: null })
        try {
          const apiConversation = await conversationsAPI.getConversation(id)

          

          // Create model lookup function to enrich messages with full model metadata
          const modelLookup = createModelLookup()
          const conversation = toFrontendConversation(apiConversation, modelLookup)

          

          set({
            activeConversation: conversation,
            activeConversationId: id,
            isLoadingConversation: false,
          })
          return conversation
        } catch (error) {
          console.error('Failed to fetch conversation:', error)
          set({ error: 'Failed to load conversation', isLoadingConversation: false })
          return null
        }
      },

      // -----------------------------------------------------------------------
      // Conversation CRUD
      // -----------------------------------------------------------------------

      createConversation: async (data?: CreateConversationRequest) => {
        set({ isSaving: true, error: null })
        try {
          const apiConversation = await conversationsAPI.createConversation(data || {})

          // Fetch full conversation with chats
          const fullConversation = await conversationsAPI.getConversation(apiConversation.id)
          const modelLookup = createModelLookup()
          const conversation = toFrontendConversation(fullConversation, modelLookup)

          // Update conversations list
          set(state => ({
            conversations: [toConversationSummary(apiConversation), ...state.conversations],
            activeConversation: conversation,
            activeConversationId: conversation.id,
            isSaving: false,
          }))

          return conversation
        } catch (error) {
          console.error('Failed to create conversation:', error)
          set({ error: 'Failed to create conversation', isSaving: false })
          throw error
        }
      },

      updateConversation: async (id: string, data: Partial<Conversation>) => {
        set({ isSaving: true, error: null })
        try {
          await conversationsAPI.updateConversation(id, {
            name: data.name,
            is_custom_name: data.isCustomName,
            is_archived: data.isArchived,
            is_pinned: data.isPinned,
            consigliere_session_id: data.consigliereSessionId,
          })

          // Update local state
          set(state => ({
            conversations: state.conversations.map(c =>
              c.id === id
                ? {
                    ...c,
                    name: data.name ?? c.name,
                    isCustomName: data.isCustomName ?? c.isCustomName,
                    isArchived: data.isArchived ?? c.isArchived,
                    isPinned: data.isPinned ?? c.isPinned,
                    updatedAt: new Date(),
                  }
                : c
            ),
            activeConversation: state.activeConversation?.id === id
              ? { ...state.activeConversation, ...data, updatedAt: new Date() }
              : state.activeConversation,
            isSaving: false,
          }))
        } catch (error) {
          console.error('Failed to update conversation:', error)
          set({ error: 'Failed to update conversation', isSaving: false })
          throw error
        }
      },

      deleteConversation: async (id: string) => {
        set({ isSaving: true, error: null })
        try {
          await conversationsAPI.deleteConversation(id)

          set(state => {
            const newConversations = state.conversations.filter(c => c.id !== id)
            const needsNewActive = state.activeConversationId === id

            return {
              conversations: newConversations,
              activeConversation: needsNewActive ? null : state.activeConversation,
              activeConversationId: needsNewActive ? null : state.activeConversationId,
              isSaving: false,
            }
          })
        } catch (error) {
          console.error('Failed to delete conversation:', error)
          set({ error: 'Failed to delete conversation', isSaving: false })
          throw error
        }
      },

      renameConversation: async (id: string, name: string) => {
        await get().updateConversation(id, { name, isCustomName: true })
      },

      // -----------------------------------------------------------------------
      // Conversation Actions
      // -----------------------------------------------------------------------

      archiveConversation: async (id: string) => {
        try {
          await conversationsAPI.archiveConversation(id)
          set(state => ({
            conversations: state.conversations.map(c =>
              c.id === id ? { ...c, isArchived: true } : c
            ),
          }))
        } catch (error) {
          console.error('Failed to archive conversation:', error)
          throw error
        }
      },

      unarchiveConversation: async (id: string) => {
        try {
          await conversationsAPI.unarchiveConversation(id)
          set(state => ({
            conversations: state.conversations.map(c =>
              c.id === id ? { ...c, isArchived: false } : c
            ),
          }))
        } catch (error) {
          console.error('Failed to unarchive conversation:', error)
          throw error
        }
      },

      pinConversation: async (id: string) => {
        try {
          await conversationsAPI.pinConversation(id)
          set(state => ({
            conversations: state.conversations.map(c =>
              c.id === id ? { ...c, isPinned: true } : c
            ),
          }))
        } catch (error) {
          console.error('Failed to pin conversation:', error)
          throw error
        }
      },

      unpinConversation: async (id: string) => {
        try {
          await conversationsAPI.unpinConversation(id)
          set(state => ({
            conversations: state.conversations.map(c =>
              c.id === id ? { ...c, isPinned: false } : c
            ),
          }))
        } catch (error) {
          console.error('Failed to unpin conversation:', error)
          throw error
        }
      },

      // -----------------------------------------------------------------------
      // Active Conversation
      // -----------------------------------------------------------------------

      setActiveConversation: async (id: string | null) => {
        if (!id) {
          set({ activeConversation: null, activeConversationId: null })
          return
        }

        // Check if we already have this conversation loaded
        const state = get()
        if (state.activeConversationId === id && state.activeConversation) {
          return
        }

        await get().fetchConversation(id)
      },

      clearActiveConversation: () => {
        set({ activeConversation: null, activeConversationId: null })
      },

      // -----------------------------------------------------------------------
      // Chat Management
      // -----------------------------------------------------------------------

      addChat: async (conversationId: string, model: Model | null, parameters?: ModelParameters, instructions?: ChatInstructions) => {


        const apiChat = await conversationsAPI.createChat(conversationId, {
          model_id: model?.model_id,
          model_provider: model?.provider,
          parameters: parameters || getDefaultParameters(),
          instructions,
        })

        

        const modelLookup = createModelLookup()
        const chat = toFrontendChat(apiChat, modelLookup)

        

        set(state => ({
          activeConversation: state.activeConversation?.id === conversationId
            ? {
                ...state.activeConversation,
                chats: [...state.activeConversation.chats, chat],
              }
            : state.activeConversation,
        }))

        return chat
      },

      updateChat: async (conversationId: string, chatId: string, data: Partial<Chat> & { position?: number }) => {
        

        await conversationsAPI.updateChat(conversationId, chatId, {
          model_id: data.model?.model_id,
          model_provider: data.model?.provider,
          parameters: data.parameters,
          position: data.position,
          is_disabled: data.disabled,
          is_hidden: data.hidden,
          instructions: data.instructions,
        })

        set(state => {
          
          return {
            activeConversation: state.activeConversation?.id === conversationId
              ? {
                  ...state.activeConversation,
                  chats: state.activeConversation.chats.map(c =>
                    c.id === chatId ? { ...c, ...data } : c
                  ),
                }
              : state.activeConversation,
          }
        })
      },

      removeChat: async (conversationId: string, chatId: string) => {
        await conversationsAPI.deleteChat(conversationId, chatId)

        set(state => ({
          activeConversation: state.activeConversation?.id === conversationId
            ? {
                ...state.activeConversation,
                chats: state.activeConversation.chats.filter(c => c.id !== chatId),
              }
            : state.activeConversation,
        }))
      },

      // -----------------------------------------------------------------------
      // Message Management
      // -----------------------------------------------------------------------

      addMessage: async (conversationId: string, chatId: string, message: CreateMessageRequest) => {
        const apiMessage = await conversationsAPI.createMessage(conversationId, chatId, message)
        const frontendMessage = toFrontendMessage(apiMessage)

        set(state => ({
          activeConversation: state.activeConversation?.id === conversationId
            ? {
                ...state.activeConversation,
                chats: state.activeConversation.chats.map(c =>
                  c.id === chatId
                    ? { ...c, messages: [...c.messages, frontendMessage] }
                    : c
                ),
              }
            : state.activeConversation,
        }))

        return frontendMessage
      },

      addMessagesBulk: async (conversationId: string, chatId: string, messages: CreateMessageRequest[]) => {
        const apiMessages = await conversationsAPI.createMessagesBulk(conversationId, chatId, { messages })
        const frontendMessages = apiMessages.map(toFrontendMessage)

        set(state => ({
          activeConversation: state.activeConversation?.id === conversationId
            ? {
                ...state.activeConversation,
                chats: state.activeConversation.chats.map(c =>
                  c.id === chatId
                    ? { ...c, messages: [...c.messages, ...frontendMessages] }
                    : c
                ),
              }
            : state.activeConversation,
        }))

        return frontendMessages
      },

      updateMessage: async (conversationId: string, chatId: string, messageId: string, data: Partial<Message>) => {
        await conversationsAPI.updateMessage(conversationId, chatId, messageId, {
          content: typeof data.content === 'string' ? { text: data.content } : data.content,
          model_id: data.model_id,
          model_provider: data.provider,
          prompt_tokens: data.tokens?.prompt,
          completion_tokens: data.tokens?.completion,
          cost: data.cost,
          tool_calls: data.tool_calls,
          steps: data.steps,
        })

        get().updateLocalMessage(chatId, messageId, data)
      },

      deleteMessage: async (conversationId: string, chatId: string, messageId: string) => {
        await conversationsAPI.deleteMessage(conversationId, chatId, messageId)

        set(state => ({
          activeConversation: state.activeConversation?.id === conversationId
            ? {
                ...state.activeConversation,
                chats: state.activeConversation.chats.map(c =>
                  c.id === chatId
                    ? { ...c, messages: c.messages.filter(m => m.message_id !== messageId) }
                    : c
                ),
              }
            : state.activeConversation,
        }))
      },

      clearMessages: async (conversationId: string, chatId: string) => {
        // Get all messages and delete them
        const state = get()
        const chat = state.activeConversation?.chats.find(c => c.id === chatId)
        if (!chat) return

        // Delete all messages (in parallel)
        await Promise.all(
          chat.messages
            .filter(m => m.message_id)
            .map(m => conversationsAPI.deleteMessage(conversationId, chatId, m.message_id!))
        )

        set(state => ({
          activeConversation: state.activeConversation?.id === conversationId
            ? {
                ...state.activeConversation,
                chats: state.activeConversation.chats.map(c =>
                  c.id === chatId ? { ...c, messages: [] } : c
                ),
              }
            : state.activeConversation,
        }))
      },

      // -----------------------------------------------------------------------
      // Local State Updates (Optimistic)
      // -----------------------------------------------------------------------

      updateLocalMessage: (chatId: string, messageId: string, data: Partial<Message>) => {
        set(state => ({
          activeConversation: state.activeConversation
            ? {
                ...state.activeConversation,
                chats: state.activeConversation.chats.map(c =>
                  c.id === chatId
                    ? {
                        ...c,
                        messages: c.messages.map(m =>
                          m.message_id === messageId ? { ...m, ...data } : m
                        ),
                      }
                    : c
                ),
              }
            : state.activeConversation,
        }))
      },

      appendLocalMessage: (chatId: string, message: Message) => {
        set(state => ({
          activeConversation: state.activeConversation
            ? {
                ...state.activeConversation,
                chats: state.activeConversation.chats.map(c =>
                  c.id === chatId
                    ? { ...c, messages: [...c.messages, message] }
                    : c
                ),
              }
            : state.activeConversation,
        }))
      },

      setChatLoading: (chatId: string, isLoading: boolean) => {
        set(state => ({
          activeConversation: state.activeConversation
            ? {
                ...state.activeConversation,
                chats: state.activeConversation.chats.map(c =>
                  c.id === chatId ? { ...c, isLoading } : c
                ),
              }
            : state.activeConversation,
        }))
      },

      // -----------------------------------------------------------------------
      // Title Generation
      // -----------------------------------------------------------------------

      startGeneratingTitle: (conversationId: string, initialName = 'New Conversation') => {
        set({
          generatingTitleForId: conversationId,
          generatingTitleText: '',
        })

        // Also update the conversation name locally
        set(state => ({
          conversations: state.conversations.map(c =>
            c.id === conversationId ? { ...c, name: initialName } : c
          ),
        }))
      },

      updateGeneratingTitle: (text: string) => {
        const state = get()
        set({
          generatingTitleText: text,
        })

        // Update conversation name in list
        if (state.generatingTitleForId) {
          set(s => ({
            conversations: s.conversations.map(c =>
              c.id === state.generatingTitleForId ? { ...c, name: text || 'New Conversation' } : c
            ),
          }))
        }
      },

      finishGeneratingTitle: async (finalTitle?: string) => {
        const state = get()
        const conversationId = state.generatingTitleForId

        if (conversationId && finalTitle) {
          try {
            await get().updateConversation(conversationId, {
              name: finalTitle,
              isCustomName: false, // Auto-generated, not custom
            })
          } catch (error) {
            console.error('Failed to save generated title:', error)
          }
        }

        set({
          generatingTitleForId: null,
          generatingTitleText: '',
        })
      },

      // -----------------------------------------------------------------------
      // Utility
      // -----------------------------------------------------------------------

      getActiveChat: () => {
        const state = get()
        if (!state.activeConversation) return null
        return state.activeConversation.chats[0] || null
      },

      refreshConversations: async () => {
        await get().fetchConversations()
      },
    }),
    { name: 'conversation-store' }
  )
)

// ============================================================================
// Helper Functions
// ============================================================================

/**
 * Creates a model lookup function that searches the model store for full model details.
 * Used to enrich messages with complete model metadata (icons, etc.) when loading conversations.
 */
function createModelLookup(): (modelId: string, provider: string) => Model | null {
  const modelState = useModelStore.getState()
  const allModels = modelState.allModels
  const favorites = modelState.favorites
  const recentModels = modelState.recentModels
  const currentModel = modelState.currentModel

  return (modelId: string, provider: string): Model | null => {
    // First try to find in allModels (most complete data)
    let model = allModels.find(m => m.model_id === modelId)
    if (model) return model as unknown as Model

    // Try to find in favorites (may have stored details)
    const favorite = favorites.find(f => f.model_id === modelId)
    if (favorite?.details) return favorite.details as unknown as Model

    // Try to find in recent models
    const recent = recentModels.find(r => r.model_id === modelId)
    if (recent?.details) return recent.details as unknown as Model

    // Try current model
    if (currentModel?.model_id === modelId) return currentModel as unknown as Model

    // Not found
    return null
  }
}

function toConversationSummary(api: APIConversation): ConversationSummary {
  // Helper to safely parse dates with fallback to current time
  const parseDate = (dateStr: string | null | undefined): Date => {
    if (!dateStr) return new Date()
    const date = new Date(dateStr)
    return isNaN(date.getTime()) ? new Date() : date
  }

  return {
    id: api.id,
    name: api.name,
    isCustomName: api.is_custom_name,
    isArchived: api.is_archived,
    isPinned: api.is_pinned,
    messageCount: api.message_count,
    chatCount: api.chat_count,
    modelId: api.model_id,
    modelProvider: api.model_provider,
    chatModels: (api.chat_models || []).map(cm => ({
      modelId: cm.model_id,
      modelProvider: cm.model_provider,
    })),
    createdAt: parseDate(api.created_at),
    updatedAt: parseDate(api.updated_at),
    lastMessageAt: api.last_message_at ? parseDate(api.last_message_at) : null,
  }
}

function getDefaultParameters(): ModelParameters {
  // Use the centralized defaults so all features are enabled
  return getDefaultModelParameters()
}

export default useConversationStore
