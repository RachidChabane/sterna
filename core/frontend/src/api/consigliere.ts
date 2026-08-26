/**
 * API integration for Consigliere AI advisor
 */

import consigliereClient from './consigliereClient'
import { fetchStream } from './transport'
import type { Chat, ChatGroup, Message } from '@/components/models/types'

// ============================================================================
// Types
// ============================================================================

/** Lightweight, non-file metadata describing one attachment on a serialized message. */
interface SerializedAttachmentMeta {
  type: 'image' | 'file'
  filename: string
  mime?: string
  size?: number
  is_pdf?: boolean
}

/**
 * A message as sent to Consigliere: timestamps and content are transport
 * strings, and attachments are replaced by lightweight metadata (no file
 * data) — see consigliereStore's serializeChatGroupForConsigliere.
 */
type ConsigliereChatMessage = Omit<Message, 'timestamp' | 'content' | 'attachments'> & {
  timestamp: string
  content: string
  attachments_meta: SerializedAttachmentMeta[]
  attachments?: undefined
}

type ConsigliereChat = Omit<Chat, 'messages'> & { messages: ConsigliereChatMessage[] }

/** A ChatGroup serialized for the Consigliere analyze request (transport-safe timestamps, no file data). */
export type ConsigliereChatGroup = Omit<ChatGroup, 'createdAt' | 'updatedAt' | 'chats'> & {
  createdAt: string
  updatedAt: string
  chats: ConsigliereChat[]
}

export interface ConsigliereMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  model_used?: string
  model_id?: string
  provider?: string
  model_icon_slug?: string
  model_icon_url?: string
  provider_icon_slug?: string
  provider_icon_url?: string
  tokens_used?: number
  prompt_tokens?: number
  completion_tokens?: number
  cost?: number
  prompt_cost?: number
  completion_cost?: number
  latency?: number
  created_at: string
}

export interface RecommendedModelFromConversation {
  model_id: string
  model_name: string
  provider: string
  reasoning: string
  score: number
  metrics: {
    total_messages: number
    avg_cost: number
    avg_latency: number
  }
  // Additional model catalog fields
  model_icon_slug?: string
  model_icon_url?: string
  provider_icon_slug?: string
  provider_icon_url?: string
  cost_per_1m_prompt?: number
  cost_per_1m_completion?: number
  max_tokens?: number
  description?: string
  is_available?: boolean
  supports_streaming?: boolean
  supports_functions?: boolean
  tags?: string[]
}

export interface ModelRecommendation {
  id: string
  model_id: string
  model_name: string
  provider: string
  score: number
  rank: number
  reasoning: string
  tradeoffs: {
    cost_savings?: string
    quality_delta?: string
    speed_delta?: string
    baseline_model_name?: string
    baseline_model_id?: string
  }
  estimated_cost_per_message?: number
  estimated_quality_score?: number
  // Additional model catalog fields
  model_icon_slug?: string
  model_icon_url?: string
  provider_icon_slug?: string
  provider_icon_url?: string
  cost_per_1m_prompt?: number
  cost_per_1m_completion?: number
  max_tokens?: number
  description?: string
  is_available?: boolean
  supports_streaming?: boolean
  supports_functions?: boolean
  tags?: string[]
}

export interface ConversationAnalysis {
  id: string
  conversation_type: string
  total_messages: number
  total_tokens: number
  avg_cost_per_message?: number
  avg_latency?: number
  total_cost: number
  insights: string[]
  detected_needs: {
    creativity?: string
    precision?: string
    speed?: string
    cost_efficiency?: string
  }
  user_preferences: Record<string, any>
  recommended_from_conversation?: RecommendedModelFromConversation
  alternative_models: ModelRecommendation[]
  recommendations: ModelRecommendation[] // deprecated - use alternative_models
  analyzed_at: string
}

export interface ConsigliereSession {
  id: string
  chat_group_id: string
  chat_group_data: ChatGroup
  current_model_at_start: string
  is_active: boolean
  created_at: string
  updated_at: string
  analysis?: ConversationAnalysis
  messages?: ConsigliereMessage[]
  message_count?: number
}

interface ConsigliereSessionSummary {
  id: string
  chat_group_id: string
  current_model_at_start: string
  is_active: boolean
  created_at: string
  updated_at: string
  has_analysis: boolean
  message_count: number
}

// ============================================================================
// Request Types
// ============================================================================

export interface AnalyzeConversationRequest {
  chat_group: ConsigliereChatGroup
  current_model: string
  user_preferences?: {
    budget_preference?: 'budget' | 'balanced' | 'premium'
    priority?: 'cost' | 'quality' | 'speed'
    max_cost_per_message?: number
  }
}

export interface ChatMessageRequest {
  session_id: string
  message: string
  current_model: string
  stream?: boolean
  parameters?: {
    temperature?: number
    max_tokens?: number
    top_p?: number
    top_k?: number
    frequency_penalty?: number
    presence_penalty?: number
    repetition_penalty?: number
    min_p?: number
    top_a?: number
  }
}

export interface ContinueSessionRequest {
  chat_group?: ChatGroup
}

export interface GenerateAnalysisRequest {
  current_model: string
}

// ============================================================================
// Progress Streaming Types
// ============================================================================

export type AnalysisStep =
  | 'preparing_context'
  | 'fetching_models'
  | 'calling_ai'
  | 'parsing_response'
  | 'calculating_costs'
  | 'saving'

export type AnalysisStepStatus = 'pending' | 'in_progress' | 'completed' | 'error'

export interface AnalysisProgressEvent {
  step: AnalysisStep
  status: AnalysisStepStatus
  message: string
  timestamp: number
}

interface AnalysisProgressUpdate {
  event: 'progress'
  data: AnalysisProgressEvent
}

interface AnalysisCompleteEvent {
  event: 'complete'
  data: {
    analysis: ConversationAnalysis
  }
}

interface AnalysisErrorEvent {
  event: 'error'
  data: {
    error: string
    detail: string
  }
}

type AnalysisStreamEvent =
  | AnalysisProgressUpdate
  | AnalysisCompleteEvent
  | AnalysisErrorEvent

// ============================================================================
// Response Types
// ============================================================================

export interface AnalyzeConversationResponse {
  session_id: string
  analysis: ConversationAnalysis
}

export interface ChatMessageResponse {
  message: ConsigliereMessage
  session_id: string
}

export interface SessionsResponse {
  sessions: ConsigliereSessionSummary[]
}

export interface RecommendationsResponse {
  recommendations: ModelRecommendation[]
}

// ============================================================================
// API Functions
// ============================================================================

export const consigliereApi = {
  /**
   * Analyze a conversation and create a new Consigliere session
   */
  async analyze(
    data: AnalyzeConversationRequest
  ): Promise<AnalyzeConversationResponse> {
    const response = await consigliereClient.post<AnalyzeConversationResponse>(
      '/analyze/',
      data
    )
    return response.data
  },

  /**
   * Delete last assistant + preceding user message, and return the user content to resend
   */
  async retryLast(sessionId: string): Promise<{ deleted_assistant_id: string; deleted_user_id: string; user_content: string }> {
    const response = await consigliereClient.post<{ deleted_assistant_id: string; deleted_user_id: string; user_content: string }>(
      `/${sessionId}/retry_last/`
    )
    return response.data
  },

  /**
   * Send a message to Consigliere and get a response
   */
  async chat(data: ChatMessageRequest): Promise<ChatMessageResponse> {
    const response = await consigliereClient.post<ChatMessageResponse>(
      '/chat/',
      data
    )
    return response.data
  },

  /**
   * Send a message to Consigliere with streaming (Server-Sent Events)
   */
  async chatStream(
    data: ChatMessageRequest,
    callbacks: {
      onContent: (content: string) => void
      onDone: (metadata: {
        usage: { prompt_tokens: number; completion_tokens: number; total_tokens: number }
        cost: number
        prompt_cost: number
        completion_cost: number
        latency: number
        message_id: string
      }) => void
      onError: (error: string) => void
    },
    opts?: { signal?: AbortSignal }
  ) {
    const response = await fetchStream(
      `${consigliereClient.defaults.baseURL}/chat_stream/`,
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ ...data, stream: true }),
        signal: opts?.signal,
      }
    )

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`)
    }

    const reader = response.body?.getReader()
    if (!reader) {
      throw new Error('Response body is not readable')
    }

    const decoder = new TextDecoder()
    let buffer = ''

    try {
      while (true) {
        const { done, value } = await reader.read()

        if (done) break

        // Decode chunk and add to buffer
        buffer += decoder.decode(value, { stream: true })

        // Process complete SSE messages (separated by double newlines)
        const messages = buffer.split('\n\n')
        buffer = messages.pop() || '' // Keep incomplete message in buffer

        for (const message of messages) {
          if (!message.trim()) continue

          // Parse SSE format: "event: <type>\ndata: <json>"
          const lines = message.split('\n')
          let eventType = 'message'
          let eventData = ''

          for (const line of lines) {
            if (line.startsWith('event: ')) {
              eventType = line.slice(7).trim()
            } else if (line.startsWith('data: ')) {
              eventData = line.slice(6)
            }
          }

          if (!eventData) continue

          try {
            const parsedData = JSON.parse(eventData)

            if (eventType === 'content') {
              callbacks.onContent(parsedData.content)
            } else if (eventType === 'done') {
              callbacks.onDone({
                usage: parsedData.usage,
                cost: parsedData.cost,
                prompt_cost: parsedData.prompt_cost,
                completion_cost: parsedData.completion_cost,
                latency: parsedData.latency,
                message_id: parsedData.message_id
              })
            } else if (eventType === 'error') {
              callbacks.onError(parsedData.error)
              throw new Error(parsedData.error)
            }
          } catch (parseError) {
            console.error('Failed to parse SSE data:', parseError)
          }
        }
      }
    } finally {
      reader.releaseLock()
    }
  },

  /**
   * Get recommendations for a session
   */
  async getRecommendations(
    sessionId: string
  ): Promise<RecommendationsResponse> {
    const response = await consigliereClient.get<RecommendationsResponse>(
      `/${sessionId}/recommendations/`
    )
    return response.data
  },

  /**
   * List user's Consigliere sessions
   */
  async listSessions(): Promise<SessionsResponse> {
    const response = await consigliereClient.get<SessionsResponse>(
      '/sessions/'
    )
    return response.data
  },

  /**
   * Get full session details
   */
  async getSession(sessionId: string): Promise<ConsigliereSession> {
    const response = await consigliereClient.get<ConsigliereSession>(
      `/${sessionId}/session/`
    )
    return response.data
  },

  /**
   * Continue a previous session with updated conversation data
   */
  async continueSession(
    sessionId: string,
    data: ContinueSessionRequest
  ): Promise<ConsigliereSession> {
    const response = await consigliereClient.post<ConsigliereSession>(
      `/${sessionId}/continue_session/`,
      data
    )
    return response.data
  },

  /**
   * Generate AI-powered analysis for an existing session
   */
  async generateAnalysis(
    sessionId: string,
    data: GenerateAnalysisRequest
  ): Promise<{ analysis: ConversationAnalysis }> {
    const response = await consigliereClient.post<{ analysis: ConversationAnalysis }>(
      `/${sessionId}/generate_analysis/`,
      data
    )
    return response.data
  },

  /**
   * Generate AI-powered analysis with real-time progress updates
   *
   * @param sessionId - Session ID
   * @param data - Analysis request data
   * @param onProgress - Callback for progress events
   * @returns Promise that resolves with the final analysis
   */
  async generateAnalysisWithProgress(
    sessionId: string,
    data: GenerateAnalysisRequest,
    onProgress?: (event: AnalysisProgressEvent) => void,
    signal?: AbortSignal
  ): Promise<ConversationAnalysis> {
    const response = await fetchStream(
      `${consigliereClient.defaults.baseURL}/${sessionId}/generate_analysis_stream/`,
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(data),
        signal,
      }
    )

    if (!response.ok) {
      throw new Error(`Failed to generate analysis: ${response.statusText}`)
    }

    const reader = response.body?.getReader()
    if (!reader) {
      throw new Error('No response body')
    }

    const decoder = new TextDecoder()
    let buffer = ''
    let finalAnalysis: ConversationAnalysis | null = null
    let streamError: Error | null = null

    try {
      while (true) {
        const { done, value } = await reader.read()

        if (done) break

        // Decode chunk and add to buffer
        buffer += decoder.decode(value, { stream: true })

        // Process complete lines (NDJSON format)
        const lines = buffer.split('\n')
        buffer = lines.pop() || '' // Keep incomplete line in buffer

        for (const line of lines) {
          if (!line.trim()) continue

          try {
            const event = JSON.parse(line) as AnalysisStreamEvent

            if (event.event === 'progress') {
              onProgress?.(event.data)
            } else if (event.event === 'complete') {
              finalAnalysis = event.data.analysis
            } else if (event.event === 'error') {
              // Store error and break out of processing
              streamError = new Error(event.data.detail || event.data.error)
              break
            }
          } catch (parseError) {
            // Only log parsing errors that are NOT from throwing the stream error
            if (!(parseError instanceof Error && parseError.message.includes('Failed to generate'))) {
              console.error('Failed to parse stream event:', line, parseError)
            }
          }
        }

        // If we encountered a stream error, break out of the read loop
        if (streamError) {
          break
        }
      }
    } finally {
      reader.releaseLock()
    }

    // If we received an error event from the stream, throw it
    if (streamError) {
      throw streamError
    }

    // Only throw "no result" error if we didn't receive an error event
    if (!finalAnalysis) {
      throw new Error('Analysis completed but no final result received')
    }

    return finalAnalysis
  },

  /**
   * Clear all messages from a Consigliere session
   */
  async clearMessages(sessionId: string): Promise<void> {
    await consigliereClient.post(`/${sessionId}/clear_messages/`)
  },
}
