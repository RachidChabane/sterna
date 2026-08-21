/**
 * Zustand store for Consigliere AI advisor state management
 */

import { create } from 'zustand'
import { consigliereApi } from '@/api/consigliere'
import { getUserFriendlyErrorMessage } from '@/utils/errorMessages'
import type {
  ConsigliereSession,
  ConversationAnalysis,
  ConsigliereMessage,
  ModelRecommendation,
  RecommendedModelFromConversation,
  AnalyzeConversationRequest,
  AnalysisStep,
  AnalysisStepStatus,
  AnalysisProgressEvent,
} from '@/api/consigliere'
import type { ChatGroup } from '@/components/models/types'
import {
  MODEL_PARAMETERS_DEFAULTS as MPD,
  getDefaultModelParameters,
} from '@/config/modelParameters'
import type { ModelParameters, Message, ChatGroup as ChatGroupType, Attachment } from '@/components/models/types'
import { extractTextFromContent } from '@/utils/chatUtils'

// Build a serializable ChatGroup for Consigliere that preserves attachment context
// without sending file contents. Adds a textual note into the user message and
// provides lightweight attachments metadata.
const serializeChatGroupForConsigliere = (group: ChatGroupType) => {
  const serializeAttachmentsMeta = (atts?: Attachment[]) => {
    if (!atts || atts.length === 0) return [] as any[]
    return atts.map((att: any) => {
      // Try enriched metadata first (fileName, fileType, fileSize), fallback to File object
      // This handles cases where File object was lost during JSON serialization
      const fileName = att.fileName || att.file?.name || 'file'
      const fileType = att.fileType || att.file?.type || undefined
      const fileSize = att.fileSize || att.file?.size || undefined

      if (att.type === 'image') {
        return {
          type: 'image',
          filename: fileName,
          mime: fileType,
          size: fileSize,
        }
      } else {
        return {
          type: 'file',
          filename: fileName,
          mime: fileType,
          size: fileSize,
          is_pdf: !!(
            (fileType === 'application/pdf') ||
            (fileName.toLowerCase().endsWith('.pdf'))
          ),
        }
      }
    })
  }

  const withAttachmentNote = (originalContent: Message['content'], atts?: Attachment[]) => {
    const baseText = extractTextFromContent(originalContent)
    if (!atts || atts.length === 0) return baseText

    const images = atts.filter((a) => a.type === 'image')
    const files = atts.filter((a) => a.type === 'file')
    // Use enriched metadata with fallback to File object
    const pdfs = files.filter((f: any) => {
      const fileType = f.fileType || f.file?.type
      const fileName = f.fileName || f.file?.name || ''
      return (fileType === 'application/pdf') || (fileName.toLowerCase().endsWith('.pdf'))
    })
    const others = files.filter((f) => !pdfs.includes(f))

    const parts: string[] = []
    if (images.length) parts.push(`${images.length} image${images.length > 1 ? 's' : ''}`)
    if (pdfs.length) parts.push(`${pdfs.length} PDF${pdfs.length > 1 ? 's' : ''}`)
    if (others.length) parts.push(`${others.length} file${others.length > 1 ? 's' : ''}`)

    const note = parts.length ? `\n\n[User attached: ${parts.join(' + ')}]` : ''
    return baseText + note
  }

  return {
    ...group,
    createdAt: group.createdAt instanceof Date ? group.createdAt.toISOString() : group.createdAt,
    updatedAt: group.updatedAt instanceof Date ? group.updatedAt.toISOString() : group.updatedAt,
    chats: group.chats.map((chat) => ({
      ...chat,
      // Ensure messages are serializable and include attachment context
      messages: chat.messages.map((m) => {
        const attachmentsMeta = serializeAttachmentsMeta(m.attachments)
        const contentWithNote = m.role === 'user'
          ? withAttachmentNote(m.content, m.attachments)
          : extractTextFromContent(m.content)

        return {
          ...m,
          // Normalize timestamp to ISO string for transport
          timestamp: m.timestamp instanceof Date ? m.timestamp.toISOString() : m.timestamp,
          // Force plain text content for the service and add attachment note for user messages
          content: contentWithNote,
          // Provide lightweight attachments metadata for downstream awareness
          attachments_meta: attachmentsMeta,
          // Drop heavy/non-serializable fields
          attachments: undefined,
        }
      }),
    })),
  } as any
}

/**
 * Normalize ConsigliereMessage to ChatPanel Message format
 */
const normalizeMessage = (msg: ConsigliereMessage): Message => {
  return {
    role: msg.role,
    content: msg.content,
    timestamp: new Date(msg.created_at),
    model: msg.model_used,
    model_id: msg.model_id,
    provider: msg.provider,
    model_icon_slug: msg.model_icon_slug,
    model_icon_url: msg.model_icon_url,
    provider_icon_slug: msg.provider_icon_slug,
    provider_icon_url: msg.provider_icon_url,
    cost: msg.cost,
    prompt_cost: msg.prompt_cost,
    completion_cost: msg.completion_cost,
    // Convert latency from seconds to milliseconds if present
    latency: msg.latency != null ? msg.latency * 1000 : undefined,
    // Convert tokens to tokens object structure
    tokens: msg.prompt_tokens != null || msg.completion_tokens != null ? {
      prompt: msg.prompt_tokens || 0,
      completion: msg.completion_tokens || 0,
    } : undefined,
  }
}

interface ConsigliereStore {
  // State
  isOpen: boolean
  currentSession: ConsigliereSession | null
  messages: ConsigliereMessage[]
  analysis: ConversationAnalysis | null
  recommendedModel: RecommendedModelFromConversation | null
  alternativeModels: ModelRecommendation[]
  recommendations: ModelRecommendation[] // deprecated - use alternativeModels
  isAnalyzing: boolean
  isGeneratingAnalysis: boolean
  isChatting: boolean
  chatAbortController: AbortController | null
  error: string | null
  analysisSteps: Record<AnalysisStep, AnalysisStepStatus>
  currentAnalysisStep: AnalysisStep | null
  analysisStepMessage: string
  parameters: ModelParameters
  abortController: AbortController | null

  // Computed
  getNormalizedMessages: () => Message[]

  // Actions
  openConsigliere: (chatGroup?: ChatGroup, currentModel?: string) => Promise<string | null>
  closeConsigliere: () => void
  analyzeConversation: (
    chatGroup: ChatGroup,
    currentModel: string,
    userPreferences?: AnalyzeConversationRequest['user_preferences']
  ) => Promise<string | null>
  generateAnalysis: (currentModel: string) => Promise<void>
  cancelAnalysis: () => void
  cancelChat: () => void
  retryLastAndResend: (
    currentModelId: string,
    currentModelData?: {
      name: string
      provider: string
      model_icon_slug?: string
      model_icon_url?: string
      provider_icon_slug?: string
      provider_icon_url?: string
    }
  ) => Promise<void>
  sendMessage: (
    content: string,
    currentModelId: string,
    currentModelData?: {
      name: string
      provider: string
      model_icon_slug?: string
      model_icon_url?: string
      provider_icon_slug?: string
      provider_icon_url?: string
    }
  ) => Promise<void>
  loadSession: (sessionId: string) => Promise<void>
  clearMessages: () => Promise<void>
  updateAnalysisStep: (event: AnalysisProgressEvent) => void
  resetAnalysisSteps: () => void
  updateParameters: (params: ModelParameters) => void
  clearError: () => void
  reset: () => void
}

export const useConsigliereStore = create<ConsigliereStore>((set, get) => ({
  // Initial state
  isOpen: false,
  currentSession: null,
  messages: [],
  analysis: null,
  recommendedModel: null,
  alternativeModels: [],
  recommendations: [], // deprecated
  isAnalyzing: false,
  isGeneratingAnalysis: false,
  isChatting: false,
  error: null,
  analysisSteps: {
    preparing_context: 'pending',
    fetching_models: 'pending',
    calling_ai: 'pending',
    parsing_response: 'pending',
    calculating_costs: 'pending',
    saving: 'pending',
  },
  currentAnalysisStep: null,
  analysisStepMessage: '',
  parameters: getDefaultModelParameters(),
  abortController: null,
  chatAbortController: null,

  // Computed
  getNormalizedMessages: () => {
    return get().messages.map(normalizeMessage)
  },

  // Open Consigliere modal
  openConsigliere: async (chatGroup?: ChatGroup, currentModel?: string) => {
    set({ isOpen: true, error: null })

    // If chatGroup has existing session, load it
    if (chatGroup?.consigliereSessionId) {
      try {
        await get().loadSession(chatGroup.consigliereSessionId)
        return chatGroup.consigliereSessionId
      } catch (error) {
        console.error('Failed to load existing session, creating new one:', error)
        // Fall through to create new session
      }
    }

    // If chatGroup and currentModel are provided, create new session
    if (chatGroup && currentModel) {
      return await get().analyzeConversation(chatGroup, currentModel)
    }

    return null
  },

  // Close Consigliere modal
  closeConsigliere: () => {
    set({ isOpen: false })
  },

  // Analyze a conversation (creates session with basic metrics only)
  analyzeConversation: async (
    chatGroup: ChatGroup,
    currentModel: string,
    userPreferences?: AnalyzeConversationRequest['user_preferences']
  ) => {
    set({ isAnalyzing: true, error: null })

    try {
      const response = await consigliereApi.analyze({
        // Send a sanitized/enriched chat group so Consigliere understands
        // when images/PDFs/files were attached, without sending file data
        chat_group: serializeChatGroupForConsigliere(chatGroup),
        current_model: currentModel,
        user_preferences: userPreferences,
      })

      // Get full session data
      const session = await consigliereApi.getSession(response.session_id)

      set({
        currentSession: session,
        analysis: response.analysis,
        recommendedModel: response.analysis.recommended_from_conversation || null,
        alternativeModels: response.analysis.alternative_models || [],
        recommendations: response.analysis.alternative_models || [], // deprecated
        messages: session.messages || [],
        isAnalyzing: false,
      })

      return response.session_id
    } catch (error: any) {
      console.error('Failed to create session:', error)
      set({
        error: getUserFriendlyErrorMessage(error),
        isAnalyzing: false,
      })
      return null
    }
  },

  // Generate AI-powered analysis with progress tracking
  generateAnalysis: async (currentModel: string) => {
    const { currentSession, updateAnalysisStep, resetAnalysisSteps } = get()

    if (!currentSession) {
      set({ error: 'No active session' })
      return
    }

    // Create AbortController for cancellation
    const controller = new AbortController()

    // Reset analysis steps before starting
    resetAnalysisSteps()
    set({ isGeneratingAnalysis: true, error: null, abortController: controller })

    try {
      const analysis = await consigliereApi.generateAnalysisWithProgress(
        currentSession.id,
        { current_model: currentModel },
        updateAnalysisStep, // Pass progress callback
        controller.signal // Pass abort signal
      )

      set({
        analysis,
        recommendedModel: analysis.recommended_from_conversation || null,
        alternativeModels: analysis.alternative_models || [],
        recommendations: analysis.alternative_models || [], // deprecated
        isGeneratingAnalysis: false,
        abortController: null,
      })
    } catch (error: any) {
      // Don't show error if it was cancelled
      if (error.name === 'AbortError') {
        
        set({ isGeneratingAnalysis: false, abortController: null })
        return
      }

      console.error('Failed to generate AI analysis:', error)
      set({
        error: getUserFriendlyErrorMessage(error),
        isGeneratingAnalysis: false,
        abortController: null,
      })
    }
  },

  // Cancel ongoing analysis
  cancelAnalysis: () => {
    const { abortController } = get()
    if (abortController) {
      abortController.abort()
      set({
        isGeneratingAnalysis: false,
        abortController: null,
        error: null,
      })
    }
  },

  // Cancel ongoing chat streaming
  cancelChat: () => {
    const { chatAbortController } = get()
    if (chatAbortController) {
      chatAbortController.abort()
      set({ isChatting: false, chatAbortController: null, error: null })
    }
  },

  // Retry: delete last assistant+user pair on backend, remove locally, then resend
  retryLastAndResend: async (currentModelId: string, currentModelData) => {
    const { currentSession } = get()
    if (!currentSession) {
      set({ error: 'No active session' })
      return
    }

    try {
      const res = await consigliereApi.retryLast(currentSession.id)

      // Remove last assistant and preceding user locally
      set((state) => {
        const msgs = [...state.messages]
        // Find last assistant index
        let aIdx = -1
        for (let i = msgs.length - 1; i >= 0; i--) {
          if (msgs[i].role === 'assistant') { aIdx = i; break }
        }
        if (aIdx === -1) return state
        // Find preceding user index
        let uIdx = -1
        for (let i = aIdx - 1; i >= 0; i--) {
          if (msgs[i].role === 'user') { uIdx = i; break }
        }
        if (uIdx === -1) return state

        const kept = msgs.filter((_, idx) => idx !== aIdx && idx !== uIdx)
        return { messages: kept }
      })

      // Resend the user message content returned by backend
      await get().sendMessage(res.user_content, currentModelId, currentModelData)
    } catch (error: any) {
      console.error('Failed to retry last message:', error)
      set({ error: getUserFriendlyErrorMessage(error) })
    }
  },

  // Send a message to Consigliere
  sendMessage: async (
    content: string,
    currentModelId: string,
    currentModelData?: {
      name: string
      provider: string
      model_icon_slug?: string
      model_icon_url?: string
      provider_icon_slug?: string
      provider_icon_url?: string
    }
  ) => {
    const { currentSession, parameters } = get()

    if (!currentSession) {
      set({ error: 'No active session' })
      return
    }

    // Optimistic update: Add user message immediately
    const userMessage: ConsigliereMessage = {
      id: `temp-user-${Date.now()}`,
      role: 'user',
      content: content,
      created_at: new Date().toISOString(),
    }

    set((state) => ({
      messages: [...state.messages, userMessage],
      isChatting: true,
      error: null,
    }))

    const startTime = Date.now()
    let accumulatedContent = ''
    const streamingMessageTimestamp = new Date().toISOString()

    try {
      // Create AbortController to allow cancelling streaming
      const controller = new AbortController()
      set({ chatAbortController: controller })

      await consigliereApi.chatStream(
        {
          session_id: currentSession.id,
          message: content,
          current_model: currentModelId,
          stream: true,
          parameters,
        },
        {
          onContent: (chunk: string) => {
            // Accumulate content as it streams in
            accumulatedContent += chunk

            // Update the message in real-time
            set((state) => {
              // Check if we already have a streaming message
              const hasStreamingMessage = state.messages.some(
                (m) => m.role === 'assistant' && m.created_at === streamingMessageTimestamp
              )

              if (hasStreamingMessage) {
                // Update existing streaming message
                return {
                  messages: state.messages.map((m) =>
                    m.role === 'assistant' && m.created_at === streamingMessageTimestamp
                      ? { ...m, content: accumulatedContent }
                      : m
                  ),
                }
              } else {
                // Create new streaming message and set isChatting to false (streaming has started)
                const streamingMessage: ConsigliereMessage = {
                  id: `temp-assistant-${Date.now()}`,
                  role: 'assistant',
                  content: accumulatedContent,
                  created_at: streamingMessageTimestamp,
                  // Add model metadata for icon display
                  model_used: currentModelData?.name,
                  model_id: currentModelId,
                  provider: currentModelData?.provider,
                  model_icon_slug: currentModelData?.model_icon_slug,
                  model_icon_url: currentModelData?.model_icon_url,
                  provider_icon_slug: currentModelData?.provider_icon_slug,
                  provider_icon_url: currentModelData?.provider_icon_url,
                }
                return {
                  messages: [...state.messages, streamingMessage],
                  isChatting: false, // Stop showing "Thinking..." once streaming starts
                }
              }
            })
          },

          onDone: (metadata) => {
            const latency = (Date.now() - startTime) / 1000 // Convert to seconds

            // Finalize the message with complete metadata
            set((state) => ({
              messages: state.messages.map((m) =>
                m.role === 'assistant' && m.created_at === streamingMessageTimestamp
                  ? {
                      ...m,
                      id: metadata.message_id,
                      content: accumulatedContent,
                      cost: metadata.cost,
                      prompt_cost: metadata.prompt_cost,
                      completion_cost: metadata.completion_cost,
                      latency: latency,
                      tokens_used: metadata.usage.total_tokens,
                      prompt_tokens: metadata.usage.prompt_tokens,
                      completion_tokens: metadata.usage.completion_tokens,
                    }
                  : m
              ),
              isChatting: false,
              chatAbortController: null,
            }))
          },

          onError: (error: string) => {
            console.error('Failed to send message:', error)

            // Add error message with model info for proper icon display
            const errorMessage: ConsigliereMessage = {
              id: `error-${Date.now()}`,
              role: 'assistant',
              content: `This model is temporarily unavailable. Please try a different model or try again later.`,
              created_at: new Date().toISOString(),
              model_used: currentModelData?.name,
              model_id: currentModelId,
              provider: currentModelData?.provider,
              model_icon_slug: currentModelData?.model_icon_slug,
              model_icon_url: currentModelData?.model_icon_url,
              provider_icon_slug: currentModelData?.provider_icon_slug,
              provider_icon_url: currentModelData?.provider_icon_url,
            }

            set((state) => ({
              messages: [...state.messages, errorMessage],
              error: error,
              isChatting: false,
              chatAbortController: null,
            }))
          },
        },
        { signal: controller.signal }
      )
    } catch (error: any) {
      // If aborted by user, stop quietly
      if (error?.name === 'AbortError') {
        set({ isChatting: false, chatAbortController: null })
        return
      }

      console.error('Failed to send message:', error)

      // Add error message with model info for proper icon display
      const errorMessage: ConsigliereMessage = {
        id: `error-${Date.now()}`,
        role: 'assistant',
        content: `This model is temporarily unavailable. Please try a different model or try again later.`,
        created_at: new Date().toISOString(),
        model_used: currentModelData?.name,
        model_id: currentModelId,
        provider: currentModelData?.provider,
        model_icon_slug: currentModelData?.model_icon_slug,
        model_icon_url: currentModelData?.model_icon_url,
        provider_icon_slug: currentModelData?.provider_icon_slug,
        provider_icon_url: currentModelData?.provider_icon_url,
      }

      set((state) => ({
        messages: [...state.messages, errorMessage],
        error: getUserFriendlyErrorMessage(error),
        isChatting: false,
        chatAbortController: null,
      }))
    }
  },

  // Load a previous session
  loadSession: async (sessionId: string) => {
    set({ isAnalyzing: true, error: null })

    try {
      const session = await consigliereApi.getSession(sessionId)

      set({
        currentSession: session,
        analysis: session.analysis || null,
        recommendedModel: session.analysis?.recommended_from_conversation || null,
        alternativeModels: session.analysis?.alternative_models || [],
        recommendations: session.analysis?.alternative_models || [], // deprecated
        messages: session.messages || [],
        isOpen: true,
        isAnalyzing: false,
      })
    } catch (error: any) {
      console.error('Failed to load session:', error)
      set({
        error: getUserFriendlyErrorMessage(error),
        isAnalyzing: false,
      })
    }
  },

  // Clear all messages from the current session
  clearMessages: async () => {
    const { currentSession } = get()

    if (!currentSession) {
      set({ error: 'No active session' })
      return
    }

    try {
      await consigliereApi.clearMessages(currentSession.id)
      set({
        messages: [],
        analysis: null,
        recommendedModel: null,
        alternativeModels: [],
        recommendations: [], // deprecated field
      })
    } catch (error: any) {
      console.error('Failed to clear messages:', error)
      set({
        error: getUserFriendlyErrorMessage(error),
      })
    }
  },

  // Update analysis step progress
  updateAnalysisStep: (event: AnalysisProgressEvent) => {
    set((state) => ({
      analysisSteps: {
        ...state.analysisSteps,
        [event.step]: event.status,
      },
      currentAnalysisStep: event.step,
      analysisStepMessage: event.message,
    }))
  },

  // Reset analysis steps to initial state
  resetAnalysisSteps: () => {
    set({
      analysisSteps: {
        preparing_context: 'pending',
        fetching_models: 'pending',
        calling_ai: 'pending',
        parsing_response: 'pending',
        calculating_costs: 'pending',
        saving: 'pending',
      },
      currentAnalysisStep: null,
      analysisStepMessage: '',
    })
  },

  // Update model parameters
  updateParameters: (params: ModelParameters) => {
    set((state) => ({
      parameters: {
        ...state.parameters,
        ...params,
      },
    }))
  },

  // Clear error
  clearError: () => {
    set({ error: null })
  },

  // Reset store
  reset: () => {
    set({
      isOpen: false,
      currentSession: null,
      messages: [],
      analysis: null,
      recommendedModel: null,
      alternativeModels: [],
      recommendations: [],
      isAnalyzing: false,
      isGeneratingAnalysis: false,
      isChatting: false,
      error: null,
      analysisSteps: {
        preparing_context: 'pending',
        fetching_models: 'pending',
        calling_ai: 'pending',
        parsing_response: 'pending',
        calculating_costs: 'pending',
        saving: 'pending',
      },
      currentAnalysisStep: null,
      analysisStepMessage: '',
      parameters: getDefaultModelParameters(),
      abortController: null,
    })
  },
}))
