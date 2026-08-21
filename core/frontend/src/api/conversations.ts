/**
 * Conversations API Client
 *
 * Handles all API calls for conversation, chat, and message management.
 * Replaces localStorage storage with PostgreSQL backend.
 */

import { api } from './client'
import type { Chat, ChatSpark, Message, ModelParameters, ChatInstructions } from '@/components/models/types'
import type { Model, WebSource } from '@/api/llm'
import { getDefaultModelParameters } from '@/config/modelParameters'

// ============================================================================
// API Response Types
// ============================================================================

/**
 * Conversation as returned from the API
 */
export interface APIChatModel {
  model_id: string
  model_provider: string | null
}

export interface APIConversation {
  id: string
  user: string
  name: string
  is_custom_name: boolean
  is_archived: boolean
  is_pinned: boolean
  consigliere_session_id: string | null
  message_count: number
  chat_count: number
  model_id: string | null
  model_provider: string | null
  chat_models?: APIChatModel[]  // All chat models for hover display
  created_at: string
  updated_at: string
  last_message_at: string | null
}

/**
 * Conversation detail with chats and messages
 */
export interface APIConversationDetail extends APIConversation {
  chats: APIChat[]
}

/**
 * Chat as returned from the API
 */
export interface APIChat {
  id: string
  conversation?: string
  model_id: string | null
  model_provider: string | null
  parameters: ModelParameters
  position: number
  is_disabled: boolean
  is_hidden: boolean
  instructions?: ChatInstructions  // Chat-specific custom instructions
  message_count: number
  messages?: APIMessage[]
  sparks?: APISpark[]  // Sparks linked to this chat (may not be linked to specific messages)
  created_at: string
  updated_at: string
}

/**
 * Spark as returned from the API (embedded in messages)
 */
export interface APISpark {
  id: string
  title: string
  framework: 'react' | 'html' | 'svg' | 'markdown' | 'mermaid' | 'pdf' | 'docx' | 'ics' | 'csv' | 'xlsx'
  code: string
  version: number
  parent_id?: string | null  // ID of the parent spark (for version tracking)
  download_url?: string | null  // For downloadable types (csv/ics/pdf/docx)
}

/**
 * Message as returned from the API
 */
export interface APIMessage {
  id: string
  chat: string
  role: 'user' | 'assistant' | 'tool' | 'system'
  content: MessageContent
  sequence: number
  model_id: string | null
  model_provider: string | null
  prompt_tokens: number | null
  completion_tokens: number | null
  cost: string | null
  tool_calls: ToolCall[]
  tool_call_id: string | null
  steps: MessageStep[]
  metadata: Record<string, unknown>
  is_stopped: boolean
  sparks: APISpark[]
  created_at: string
}

// Content types — keep in sync with MessageContentPart in
// components/models/types.ts (includes the asset_ref variant used for
// uploaded attachments referenced by asset id).
type MessageContentPart =
  | { type: 'text'; text: string }
  | { type: 'image_url'; image_url: { url: string } }
  | { type: 'file'; file: { filename: string; file_data: string } }
  | { type: 'asset_ref'; asset_id: string; filename: string; mime_type: string; asset_type: string; width?: number; height?: number; download_url: string }

type MessageContent = string | { text?: string } | MessageContentPart[]

interface ToolCall {
  id: string
  type: 'function'
  function: {
    name: string
    arguments: string
  }
}

interface MessageStep {
  type: string
  content?: string
  isStreaming?: boolean
  executions?: unknown[]
}

// ============================================================================
// Request Types
// ============================================================================

export interface CreateConversationRequest {
  name?: string
  is_custom_name?: boolean
  consigliere_session_id?: string
  model_id?: string
  model_provider?: string
  parameters?: ModelParameters
}

export interface UpdateConversationRequest {
  name?: string
  is_custom_name?: boolean
  is_archived?: boolean
  is_pinned?: boolean
  consigliere_session_id?: string
}

export interface CreateChatRequest {
  model_id?: string
  model_provider?: string
  parameters?: ModelParameters
  position?: number
  instructions?: ChatInstructions
}

export interface UpdateChatRequest {
  model_id?: string
  model_provider?: string
  parameters?: ModelParameters
  position?: number
  is_disabled?: boolean
  is_hidden?: boolean
  instructions?: ChatInstructions
}

export interface CreateMessageRequest {
  role: 'user' | 'assistant' | 'tool' | 'system'
  content: MessageContent
  model_id?: string
  model_provider?: string
  prompt_tokens?: number
  completion_tokens?: number
  cost?: number | string  // Django DecimalField expects string for precision
  tool_calls?: ToolCall[]
  tool_call_id?: string
  steps?: MessageStep[]
  metadata?: Record<string, unknown>
  is_stopped?: boolean
}

export interface BulkCreateMessagesRequest {
  messages: CreateMessageRequest[]
}

// Search types
export interface SearchResult {
  conversation: APIConversation
  snippet: string
  message_role: 'user' | 'assistant' | 'tool' | 'system'
  message_model_id: string | null
  message_model_provider: string | null
  message_created_at: string
}

export interface SearchResponse {
  count: number
  page: number
  page_size: number
  results: SearchResult[]
}

// ============================================================================
// API Client
// ============================================================================

export interface PaginatedConversationsResponse {
  count: number
  next: string | null
  previous: string | null
  results: APIConversation[]
}

export const conversationsAPI = {
  // -------------------------------------------------------------------------
  // Conversations
  // -------------------------------------------------------------------------

  /**
   * List all conversations for the current user
   */
  async listConversations(params?: {
    is_archived?: boolean
    is_pinned?: boolean
    search?: string
    ordering?: string
  }): Promise<APIConversation[]> {
    const response = await api.get('/conversations/', { params })
    return response.data.results || response.data
  },

  /**
   * List conversations with pagination support
   */
  async listConversationsPaginated(params?: {
    page?: number
    page_size?: number
    is_archived?: boolean
    is_pinned?: boolean
    search?: string
    ordering?: string
  }): Promise<PaginatedConversationsResponse> {
    const response = await api.get('/conversations/', { params })
    return {
      count: response.data.count || 0,
      next: response.data.next || null,
      previous: response.data.previous || null,
      results: response.data.results || response.data || [],
    }
  },

  /**
   * Get a single conversation with all chats and messages
   */
  async getConversation(id: string): Promise<APIConversationDetail> {
    
    const response = await api.get(`/conversations/${id}/`)
    const data = response.data as APIConversationDetail
    // Log what we received for debugging
    
    return data
  },

  /**
   * Create a new conversation
   */
  async createConversation(data: CreateConversationRequest): Promise<APIConversation> {
    const response = await api.post('/conversations/', data)
    return response.data
  },

  /**
   * Update a conversation
   */
  async updateConversation(id: string, data: UpdateConversationRequest): Promise<APIConversation> {
    const response = await api.patch(`/conversations/${id}/`, data)
    return response.data
  },

  /**
   * Delete a conversation
   */
  async deleteConversation(id: string): Promise<void> {
    await api.delete(`/conversations/${id}/`)
  },

  /**
   * Archive a conversation
   */
  async archiveConversation(id: string): Promise<void> {
    await api.post(`/conversations/${id}/archive/`)
  },

  /**
   * Unarchive a conversation
   */
  async unarchiveConversation(id: string): Promise<void> {
    await api.post(`/conversations/${id}/unarchive/`)
  },

  /**
   * Pin a conversation
   */
  async pinConversation(id: string): Promise<void> {
    await api.post(`/conversations/${id}/pin/`)
  },

  /**
   * Unpin a conversation
   */
  async unpinConversation(id: string): Promise<void> {
    await api.post(`/conversations/${id}/unpin/`)
  },

  /**
   * Generate name from first message
   */
  async generateName(id: string): Promise<APIConversation> {
    const response = await api.post(`/conversations/${id}/generate_name/`)
    return response.data
  },

  /**
   * Search conversations by message content
   */
  async searchConversations(
    query: string,
    page: number = 1,
    pageSize: number = 20
  ): Promise<SearchResponse> {
    const response = await api.get('/conversations/search/', {
      params: { q: query, page, page_size: pageSize }
    })
    return response.data
  },

  /**
   * Save conversation to knowledge base as a markdown document
   */
  async saveToKnowledgeBase(conversationId: string): Promise<{
    document_id: string
    filename: string
    status: string
    message: string
  }> {
    const response = await api.post(`/conversations/${conversationId}/save_to_knowledge_base/`)
    return response.data
  },

  // -------------------------------------------------------------------------
  // Chats
  // -------------------------------------------------------------------------

  /**
   * List chats in a conversation
   */
  async listChats(conversationId: string): Promise<APIChat[]> {
    const response = await api.get(`/conversations/${conversationId}/chats/`)
    return response.data.results || response.data
  },

  /**
   * Get a single chat with messages
   */
  async getChat(conversationId: string, chatId: string): Promise<APIChat> {
    const response = await api.get(`/conversations/${conversationId}/chats/${chatId}/`)
    return response.data
  },

  /**
   * Create a new chat in a conversation
   */
  async createChat(conversationId: string, data: CreateChatRequest): Promise<APIChat> {
    const response = await api.post(`/conversations/${conversationId}/chats/`, data)
    return response.data
  },

  /**
   * Update a chat
   */
  async updateChat(conversationId: string, chatId: string, data: UpdateChatRequest): Promise<APIChat> {
    
    try {
      const response = await api.patch(`/conversations/${conversationId}/chats/${chatId}/`, data)
      
      return response.data
    } catch (error: any) {
      console.error(`[conversationsAPI] ❌ Failed to update chat:`, {
        conversationId,
        chatId,
        error: error.message,
        status: error.response?.status,
      })
      throw error
    }
  },

  /**
   * Delete a chat
   */
  async deleteChat(conversationId: string, chatId: string): Promise<void> {
    await api.delete(`/conversations/${conversationId}/chats/${chatId}/`)
  },

  // -------------------------------------------------------------------------
  // Messages
  // -------------------------------------------------------------------------

  /**
   * List messages in a chat
   */
  async listMessages(conversationId: string, chatId: string): Promise<APIMessage[]> {
    const response = await api.get(
      `/conversations/${conversationId}/chats/${chatId}/messages/`
    )
    return response.data.results || response.data
  },

  /**
   * Create a new message
   */
  async createMessage(
    conversationId: string,
    chatId: string,
    data: CreateMessageRequest
  ): Promise<APIMessage> {
    
    try {
      const response = await api.post(
        `/conversations/${conversationId}/chats/${chatId}/messages/`,
        data
      )
      
      return response.data
    } catch (error: any) {
      console.error(`[conversationsAPI] ❌ Failed to create message:`, {
        conversationId,
        chatId,
        error: error.message,
        status: error.response?.status,
        // Log the full error response for debugging
        validationErrors: error.response?.data,
      })
      // Log the raw error data separately for easier reading
      if (error.response?.data) {
        console.error(`[conversationsAPI] Validation errors:`, JSON.stringify(error.response.data, null, 2))
      }
      throw error
    }
  },

  /**
   * Create multiple messages at once
   */
  async createMessagesBulk(
    conversationId: string,
    chatId: string,
    data: BulkCreateMessagesRequest
  ): Promise<APIMessage[]> {
    const response = await api.post(
      `/conversations/${conversationId}/chats/${chatId}/messages/bulk/`,
      data
    )
    return response.data
  },

  /**
   * Update a message
   */
  async updateMessage(
    conversationId: string,
    chatId: string,
    messageId: string,
    data: Partial<CreateMessageRequest>
  ): Promise<APIMessage> {
    const response = await api.patch(
      `/conversations/${conversationId}/chats/${chatId}/messages/${messageId}/`,
      data
    )
    return response.data
  },

  /**
   * Delete a message
   */
  async deleteMessage(conversationId: string, chatId: string, messageId: string): Promise<void> {
    await api.delete(
      `/conversations/${conversationId}/chats/${chatId}/messages/${messageId}/`
    )
  },
}

// ============================================================================
// Type Conversion Utilities
// ============================================================================

/**
 * Helper to safely parse dates with fallback to current time
 */
function parseDate(dateStr: string | null | undefined): Date {
  if (!dateStr) return new Date()
  const date = new Date(dateStr)
  return isNaN(date.getTime()) ? new Date() : date
}

/**
 * Convert API conversation to frontend ChatGroup format
 */
export function toFrontendConversation(
  apiConversation: APIConversationDetail,
  modelLookup?: (modelId: string, provider: string) => Model | null
): {
  id: string
  name: string
  createdAt: Date
  updatedAt: Date
  chats: Chat[]
  isCustomName?: boolean
  consigliereSessionId?: string
} {
  return {
    id: apiConversation.id,
    name: apiConversation.name,
    createdAt: parseDate(apiConversation.created_at),
    updatedAt: parseDate(apiConversation.updated_at),
    isCustomName: apiConversation.is_custom_name,
    consigliereSessionId: apiConversation.consigliere_session_id || undefined,
    chats: apiConversation.chats.map(chat => toFrontendChat(chat, modelLookup)),
  }
}

/**
 * Convert API chat to frontend Chat format
 * Optionally accepts a modelLookup function to resolve full model details including icons
 */
export function toFrontendChat(
  apiChat: APIChat,
  modelLookup?: (modelId: string, provider: string) => Model | null
): Chat {
  // Try to get full model info from lookup, fallback to minimal model
  let chatModel: Model | null = null
  if (apiChat.model_id) {
    if (modelLookup) {
      chatModel = modelLookup(apiChat.model_id, apiChat.model_provider || 'unknown')
    }
    // Fallback to minimal model if lookup fails or not provided
    if (!chatModel) {
      chatModel = {
        id: apiChat.model_id,
        model_id: apiChat.model_id,
        provider: apiChat.model_provider || 'unknown',
        name: apiChat.model_id,
      } as Model
    }
  }

  // Convert messages and enrich assistant messages with model info
  // Each message may have its own model_id (different from the chat's current model)
  const messages = apiChat.messages?.map(msg => {
    const frontendMsg = toFrontendMessage(msg)

    // Enrich assistant messages with model metadata
    if (frontendMsg.role === 'assistant') {
      // Prefer the message's own model_id, fall back to chat's model
      const messageModelId = msg.model_id || apiChat.model_id
      const messageProvider = msg.model_provider || apiChat.model_provider || 'unknown'

      // Try to look up the message's model for full metadata (icons, etc.)
      let messageModel: Model | null = null
      if (messageModelId && modelLookup) {
        messageModel = modelLookup(messageModelId, messageProvider)
      }

      // Use looked-up model, or fallback to chat model, or create minimal model
      const modelToUse = messageModel || (messageModelId === apiChat.model_id ? chatModel : null)

      if (modelToUse) {
        return {
          ...frontendMsg,
          model: modelToUse.name,
          model_id: modelToUse.model_id,
          provider: modelToUse.provider,
          provider_icon_slug: (modelToUse as any).provider_icon_slug,
          provider_icon_url: (modelToUse as any).provider_icon_url,
          model_icon_slug: (modelToUse as any).model_icon_slug,
          model_icon_url: (modelToUse as any).model_icon_url,
        }
      } else if (messageModelId) {
        // Create minimal model metadata from what we have
        return {
          ...frontendMsg,
          model: messageModelId,
          model_id: messageModelId,
          provider: messageProvider,
        }
      }
    }
    return frontendMsg
  }) || []

  // Convert chat-level sparks
  const chatSparks = apiChat.sparks?.map(spark => ({
    id: spark.id,
    title: spark.title,
    framework: spark.framework,
    code: spark.code,
    version: spark.version,
    parent_id: spark.parent_id,
    download_url: spark.download_url,
  })) || []

  return {
    id: apiChat.id,
    model: chatModel,
    messages,
    isLoading: false,
    parameters: apiChat.parameters || getDefaultParameters(),
    disabled: apiChat.is_disabled,
    hidden: apiChat.is_hidden,
    instructions: apiChat.instructions,
    sparks: chatSparks,
  }
}

/**
 * Asset reference stored in message content
 */
interface AssetRefPart {
  type: 'asset_ref'
  asset_id: string
  filename: string
  mime_type: string
  asset_type: string
  size_bytes?: number
  width?: number
  height?: number
  download_url: string
}

/**
 * Reconstructed attachment from asset reference
 */
interface ReconstructedAttachment {
  id: string
  type: 'image' | 'file' | 'video' | 'audio'
  file: { name: string; type: string; size: number }
  assetId: string
  assetUrl: string
  // For images/video/audio, the preview will be the download URL
  preview?: string
}

/**
 * Convert API message to frontend Message format
 */
export function toFrontendMessage(apiMessage: APIMessage): Message {
  // Extract text from content and asset references
  let contentText = ''
  const attachments: ReconstructedAttachment[] = []

  if (typeof apiMessage.content === 'string') {
    contentText = apiMessage.content
  } else if (apiMessage.content && typeof apiMessage.content === 'object') {
    if ('text' in apiMessage.content) {
      contentText = (apiMessage.content as { text?: string }).text || ''
    } else if (Array.isArray(apiMessage.content)) {
      // Process multipart content
      for (const part of apiMessage.content) {
        if (part.type === 'text' && 'text' in part) {
          contentText = part.text
        } else if (part.type === 'asset_ref') {
          // Convert asset reference to attachment for display
          const assetPart = part as unknown as AssetRefPart
          // SVG files are XML-based and should be treated as text/code, not images
          const isSVG = assetPart.mime_type === 'image/svg+xml' || assetPart.filename.toLowerCase().endsWith('.svg')
          // Determine attachment type from mime_type
          const isImage = assetPart.mime_type.startsWith('image/') && !isSVG
          const isVideo = assetPart.mime_type.startsWith('video/')
          const isAudio = assetPart.mime_type.startsWith('audio/')

          let attType: 'image' | 'video' | 'audio' | 'file' = 'file'
          if (isImage) attType = 'image'
          else if (isVideo) attType = 'video'
          else if (isAudio) attType = 'audio'

          attachments.push({
            id: assetPart.asset_id,
            type: attType,
            file: {
              name: assetPart.filename,
              type: assetPart.mime_type,
              size: assetPart.size_bytes || 0,
            },
            assetId: assetPart.asset_id,
            assetUrl: assetPart.download_url,
            preview: (isImage || isVideo || isAudio) ? assetPart.download_url : undefined,
          })
        }
      }
    }
  }

  // Extract web_sources from metadata if present
  const webSources = apiMessage.metadata?.web_sources as WebSource[] | undefined

  // Extract sparks from API response (persisted sparks from database)
  const sparks = apiMessage.sparks?.map(spark => ({
    id: spark.id,
    title: spark.title,
    framework: spark.framework,
    code: spark.code,
    version: spark.version,
    parent_id: spark.parent_id,
    download_url: spark.download_url,
  })) || []

  // Sanitize steps to clear any stale isExecuting flags (persisted state shouldn't be "executing")
  const sanitizedSteps = apiMessage.steps?.map((step: any) => {
    if (step.type === 'tool_executions') {
      return {
        ...step,
        isExecuting: false,
        executions: step.executions?.map((exec: any) => ({
          ...exec,
          isExecuting: false,
        })),
      }
    }
    if (step.type === 'reasoning') {
      return {
        ...step,
        isStreaming: false,
      }
    }
    return step
  })

  return {
    role: apiMessage.role as 'user' | 'assistant' | 'tool',
    content: contentText,
    timestamp: parseDate(apiMessage.created_at),
    message_id: apiMessage.id,
    model_id: apiMessage.model_id || undefined,
    provider: apiMessage.model_provider || undefined,
    tokens: apiMessage.prompt_tokens || apiMessage.completion_tokens ? {
      prompt: apiMessage.prompt_tokens || 0,
      completion: apiMessage.completion_tokens || 0,
    } : undefined,
    cost: apiMessage.cost ? parseFloat(apiMessage.cost) : undefined,
    tool_calls: apiMessage.tool_calls || undefined,
    tool_call_id: apiMessage.tool_call_id || undefined,
    steps: sanitizedSteps as Message['steps'] || undefined,
    // Include reconstructed attachments if any
    attachments: attachments.length > 0 ? attachments as any : undefined,
    // Include web sources from metadata
    web_sources: webSources,
    // Include sparks (interactive React components)
    sparks: sparks.length > 0 ? sparks : undefined,
    // Map is_stopped flag for stopped messages
    is_stopped: apiMessage.is_stopped || false,
    isInterrupted: apiMessage.is_stopped || false,
  }
}

/**
 * Get default model parameters
 */
function getDefaultParameters(): ModelParameters {
  // Use the centralized defaults so all features are enabled
  return getDefaultModelParameters()
}

export default conversationsAPI
