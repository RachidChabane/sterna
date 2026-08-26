/**
 * LLM completion and model-catalog client.
 *
 * Model/ModelsResponse/ModelStatsResponse describe REST responses the
 * OpenAPI schema has a component for, but the schema's operation for
 * each is annotated with the model catalog ViewSet's default
 * serializer rather than the response the underlying custom action
 * actually returns, so the generated types do not describe them
 * either; these stay hand-written against the API. The streaming
 * completion request/response and coding-agent event types live in
 * ./hand-written/streaming and are re-exported below.
 */
import apiClient, { handleUnauthorized } from './client'
import { fetchStream } from './transport'
import type {
  CompletionMessage,
  CompletionRequest,
  CompletionUsage,
  WebSource,
  CodingAgentStep,
  CodingAgentQuestion,
  CodingAgentResult,
  ContextCompactedData,
  SternaRouteData,
  CompletionResponse,
} from './hand-written/streaming'
export type {
  CompletionMessage,
  CompletionRequest,
  CompletionUsage,
  WebSource,
  CodingAgentStep,
  CodingAgentQuestion,
  CodingAgentResult,
  ContextCompactedData,
  SternaRouteData,
  CompletionResponse,
}

export interface Model {
  id: string                    // Backend ModelCatalog UUID (serializer includes it)
  model_id: string
  name: string
  provider: string
  provider_icon_slug?: string
  provider_icon_url?: string
  model_icon_slug?: string
  model_icon_url?: string
  cost_per_1m_prompt: number | null
  cost_per_1m_completion: number | null
  max_tokens: number
  supports_streaming: boolean
  supports_functions: boolean
  supports_structured_outputs: boolean
  supports_reasoning: boolean
  supports_prompt_caching: boolean
  supports_stream_cancellation: boolean
  input_modalities: string[]
  output_modalities?: string[]
  tags?: string[]
  is_available: boolean
  is_new?: boolean              // True if model was first seen within 48h
  first_seen_at?: string | null // ISO timestamp of when model was first seen
}

export interface ModelsResponse {
  results: Model[]
  count: number
  next: string | null
  previous: string | null
}

export interface ModelStatsResponse {
  total_models: number
  available_models: number
  total_providers: number
  providers_list: string[]
  cost_percentiles: {
    p10: number
    p40: number
    p70: number
    p95: number
    p99: number
  }
}

export const llmApi = {
  // Get available models
  models: (params?: {
    page?: number
    search?: string
    provider?: string
    available_only?: boolean
    min_context_length?: number
    supports_functions?: boolean
    supports_streaming?: boolean
    tags?: string[]
  }) =>
    apiClient.get<ModelsResponse>('/llm/models/', { params }),

  // Get model stats
  modelStats: () =>
    apiClient.get<ModelStatsResponse>('/llm/models/stats/'),

  // Complete with single model
  complete: (data: CompletionRequest) =>
    apiClient.post<CompletionResponse>('/llm/completions/complete/', data),

  // Complete with streaming (Server-Sent Events)
  completeStream: async (
    data: CompletionRequest,
    callbacks: {
      onContent: (content: string) => void
      onReasoning?: (content: string) => void
      onToolCallRequest?: (approvals: any[], toolCalls: any[]) => void
      onWebSources?: (sources: WebSource[]) => void
      onImage?: (imageData: string) => void
      onFileToolExecuting?: (toolCalls: any[]) => void
      onFileToolExecuted?: (toolCalls: any[], results: any[]) => void
      onCodingAgentStep?: (step: CodingAgentStep) => void
      onCodingAgentCompleted?: (result: CodingAgentResult) => void
      onCodingAgentQuestion?: (data: CodingAgentQuestion) => void
      onContextCompacted?: (data: ContextCompactedData) => void
      onPreviewStarted?: (data: { port: number; command: string; pid: number }) => void
      onSparks?: (sparks: Array<{ id: string; title: string; framework: 'react' | 'html' | 'svg' | 'markdown' | 'mermaid' | 'pdf' | 'docx' | 'ics' | 'csv' | 'xlsx'; code: string; version: number }>) => void
      onSternaRoute?: (data: SternaRouteData) => void
      onGenerationId?: (generationId: string) => void
      onUsageUpdate?: (data: { usage: CompletionUsage; cost: number; prompt_cost: number; completion_cost: number; generation_id?: string; generation_ids?: string[] }) => void
      onDone: (metadata: { usage: CompletionUsage; cost: number; prompt_cost: number; completion_cost: number; model: string; finish_reason?: string; reasoning_content?: string; images?: string[]; sparks?: Array<{ id: string; title: string; framework: 'react' | 'html' | 'svg' | 'markdown' | 'mermaid' | 'pdf' | 'docx' | 'ics' | 'csv' | 'xlsx'; code: string; version: number }>; generation_id?: string; generation_ids?: string[] }) => void
      onError: (error: string, detail?: string, code?: string) => void
    },
    options?: { controller?: AbortController; uploadedFiles?: File[] }
  ) => {
    const baseURL = apiClient.defaults.baseURL || ''

    // Set up timeout controller (2 minutes)
    const controller = options?.controller ?? new AbortController()
    const timeoutId = setTimeout(() => controller.abort(), 120000)

    try {
      // Check if we have uploaded files - use FormData if yes, JSON if no
      const hasUploadedFiles = options?.uploadedFiles && options.uploadedFiles.length > 0

      let requestBody: FormData | string
      let requestHeaders: Record<string, string>

      if (hasUploadedFiles) {
        // Use FormData for file uploads
        const formData = new FormData()

        // Add scalar fields
        formData.append('model', data.model)
        formData.append('temperature', String(data.temperature ?? 0.7))
        formData.append('enable_file_tools', String(data.enable_file_tools ?? false))
        formData.append('enable_mcp_tools', String(data.enable_mcp_tools ?? false))
        formData.append('enable_brave_search', String(data.enable_brave_search ?? false))
        formData.append('enable_image_generation', String(data.enable_image_generation ?? false))
        formData.append('enable_video_generation', String(data.enable_video_generation ?? false))
        formData.append('enable_reasoning', String(data.enable_reasoning ?? false))
        formData.append('enable_sparks', String(data.enable_sparks ?? false))
        formData.append('enable_knowledge_base', String(data.enable_knowledge_base ?? false))
        if (data.enable_voice_mode) formData.append('enable_voice_mode', String(data.enable_voice_mode))

        if (data.conversation_id) formData.append('conversation_id', data.conversation_id)
        if (data.chat_id) formData.append('chat_id', data.chat_id)
        if (data.message_id) formData.append('message_id', data.message_id)
        if (data.max_tokens) formData.append('max_tokens', String(data.max_tokens))
        if (data.top_p) formData.append('top_p', String(data.top_p))
        if (data.stream !== undefined) formData.append('stream', String(data.stream))
        if (data.reasoning_effort) formData.append('reasoning_effort', data.reasoning_effort)
        if (data.reasoning_max_tokens) formData.append('reasoning_max_tokens', String(data.reasoning_max_tokens))
        if (data.spark_fix_request) formData.append('spark_fix_request', JSON.stringify(data.spark_fix_request))
        if (data.sterna_strength) formData.append('sterna_strength', data.sterna_strength)
        if (data.system_prompt) formData.append('system_prompt', data.system_prompt)
        if (data.plugins) formData.append('plugins', JSON.stringify(data.plugins))

        // Add asset-backed files for workspace copy (no File object available)
        if (data.workspace_assets) {
          formData.append('workspace_assets', JSON.stringify(data.workspace_assets))
        }

        // Add messages as JSON string
        formData.append('messages', JSON.stringify(data.messages))

        // Add uploaded files
        options.uploadedFiles!.forEach((file) => {
          formData.append('files', file)
        })

        requestBody = formData
        // Don't set Content-Type - browser sets it automatically with boundary
        requestHeaders = {}
      } else {
        // Use JSON for regular requests (no files)
        requestBody = JSON.stringify(data)
        requestHeaders = {
          'Content-Type': 'application/json',
        }
      }

      // Make the streaming request (V2: LangChain-based with proper tool calling loop).
      // fetchStream attaches the bearer token and retries once via refresh
      // on a 401; a thrown "Session expired" error means that retry itself
      // couldn't recover (no/failed refresh), which already triggered the
      // centralized session-expired modal — surface it through onError the
      // same way the pre-retry 401 branch below does.
      let response: Response
      try {
        response = await fetchStream(`${baseURL}/llm/completions/stream-complete-v2/`, {
          method: 'POST',
          headers: requestHeaders,
          body: requestBody,
          signal: controller.signal
        })
      } catch (err) {
        clearTimeout(timeoutId)
        if (err instanceof Error && err.message.startsWith('Session expired')) {
          callbacks.onError('Session expired', 'Your session has expired. Please sign in again to continue.')
          return
        }
        throw err
      }

      // Clear timeout after successful connection
      clearTimeout(timeoutId)

      // Check response status
      if (!response.ok) {
        // Handle 401 Unauthorized - session expired
        if (response.status === 401) {
          handleUnauthorized()
          callbacks.onError('Session expired', 'Your session has expired. Please sign in again to continue.')
          return
        }

        throw new Error(`HTTP error! status: ${response.status}`)
      }

      // Get reader from response body
      const reader = response.body?.getReader()
      if (!reader) {
        throw new Error('Response body is not readable')
      }

      // Initialize streaming state
      const decoder = new TextDecoder()
      let buffer = ''
      let receivedDone = false

      try {
        // Read stream chunks
        while (true) {
          const { done, value } = await reader.read()

          // Check if stream ended
          if (done) {
            // Verify we received 'done' event (skip check if user aborted)
            if (!receivedDone && !controller.signal.aborted) {
              console.error('[SSE] Stream ended without done event')
              callbacks.onError(
                'Stream ended unexpectedly',
                'The model stopped responding without completing the request. This may be due to a timeout or network issue.'
              )
            }
            break
          }

          // Decode chunk and add to buffer
          buffer += decoder.decode(value, { stream: true })

          // Process complete SSE messages (separated by double newlines)
          const messages = buffer.split('\n\n')
          buffer = messages.pop() || '' // Keep incomplete message in buffer

          // Process each complete message
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

            // Parse JSON data
            try {
              const data = JSON.parse(eventData)

              // Handle different event types
              if (eventType === 'content') {
                callbacks.onContent(data.content)
              } else if (eventType === 'reasoning') {
                // Handle reasoning chunks (thinking process)
                if (callbacks.onReasoning) {
                  callbacks.onReasoning(data.content)
                }
              } else if (eventType === 'tool_call_request') {
                // Handle tool call approval requests
                if (callbacks.onToolCallRequest) {
                  callbacks.onToolCallRequest(data.approvals || [], data.tool_calls || [])
                }
              } else if (eventType === 'web_sources') {
                // Handle web search sources
                if (callbacks.onWebSources) {
                  callbacks.onWebSources(data.sources || [])
                }
              } else if (eventType === 'image') {
                // Handle generated images from image generation models
                if (callbacks.onImage && data.image) {
                  
                  callbacks.onImage(data.image)
                }
              } else if (eventType === 'file_tool_executing') {
                // Handle file tool execution START (loading state)
                
                if (callbacks.onFileToolExecuting) {
                  callbacks.onFileToolExecuting(data.tool_calls || [])
                } else {
                  console.warn('[SSE] onFileToolExecuting callback not defined!')
                }
              } else if (eventType === 'file_tool_executed') {
                // Handle file tool execution results (completed state)
                if (callbacks.onFileToolExecuted) {
                  callbacks.onFileToolExecuted(data.tool_calls || [], data.results || [])
                }
              } else if (eventType === 'coding_agent_step') {
                // Handle Coding Agent agent step progress
                if (callbacks.onCodingAgentStep) {
                  callbacks.onCodingAgentStep({
                    job_id: data.job_id,
                    step_index: data.step_index,
                    type: data.type,
                    tool: data.tool,
                    content: data.content,
                    timestamp: data.timestamp,
                  })
                }
              } else if (eventType === 'coding_agent_completed') {
                // Handle Coding Agent agent completion
                if (callbacks.onCodingAgentCompleted) {
                  callbacks.onCodingAgentCompleted({
                    job_id: data.job_id,
                    success: data.success,
                    summary: data.summary,
                    files_modified: data.files_modified || [],
                    files_created: data.files_created || [],
                    error: data.error,
                    duration_ms: data.duration_ms || 0,
                    total_tokens: data.total_tokens,
                    steps: data.steps,
                  })
                }
              } else if (eventType === 'coding_agent_question') {
                // Handle Coding Agent question (ask_user MCP tool)
                if (callbacks.onCodingAgentQuestion) {
                  callbacks.onCodingAgentQuestion({
                    question: data.question,
                    options: data.options,
                  })
                }
              } else if (eventType === 'preview_started') {
                // Handle preview server started
                if (callbacks.onPreviewStarted) {
                  callbacks.onPreviewStarted({
                    port: data.port,
                    command: data.command,
                    pid: data.pid,
                  })
                }
              } else if (eventType === 'context_compacted') {
                // Handle context compaction notification
                if (callbacks.onContextCompacted) {
                  callbacks.onContextCompacted({
                    original_messages: data.original_messages,
                    compacted_messages: data.compacted_messages,
                    original_tokens: data.original_tokens,
                    compacted_tokens: data.compacted_tokens,
                    tokens_saved: data.tokens_saved,
                    compression_ratio: data.compression_ratio,
                    duration_ms: data.duration_ms,
                  })
                }
              } else if (eventType === 'sparks') {
                // Handle sparks (interactive components)
                if (callbacks.onSparks && data.sparks) {
                  callbacks.onSparks(data.sparks)
                }
              } else if (eventType === 'sterna_route' || eventType === 'sterna_reroute') {
                if (callbacks.onSternaRoute) {
                  callbacks.onSternaRoute(data as SternaRouteData)
                }
              } else if (eventType === 'generation_id') {
                if (callbacks.onGenerationId && data.generation_id) {
                  callbacks.onGenerationId(data.generation_id)
                }
              } else if (eventType === 'usage_update') {
                if (callbacks.onUsageUpdate) {
                  callbacks.onUsageUpdate({
                    usage: data.usage,
                    cost: data.cost,
                    prompt_cost: data.prompt_cost,
                    completion_cost: data.completion_cost,
                    generation_id: data.generation_id,
                    generation_ids: data.generation_ids,
                  })
                }
              } else if (eventType === 'done') {
                receivedDone = true

                callbacks.onDone({
                  usage: data.usage,
                  cost: data.cost,
                  prompt_cost: data.prompt_cost,
                  completion_cost: data.completion_cost,
                  model: data.model,
                  finish_reason: data.finish_reason,
                  reasoning_content: data.reasoning_content,
                  images: data.images,
                  sparks: data.sparks,
                  generation_id: data.generation_id,
                  generation_ids: data.generation_ids,
                })
              } else if (eventType === 'error') {
                console.error('[SSE ERROR] Received error event:', {
                  error: data.error,
                  message: data.message,
                  detail: data.detail,
                  eventType
                })
                // Mark stream as completed to prevent duplicate error on stream end
                receivedDone = true
                // Prefer 'message' (user-friendly) over 'error' (often just a code like "quota_exceeded")
                callbacks.onError(data.message || data.error, data.detail, data.code)
                // No throw - let stream end naturally to avoid duplicate error
              }
            } catch (parseError) {
              console.error('[SSE] Failed to parse SSE data:', parseError)
            }
          }
        }
      } finally {
        // Always release the reader lock
        reader.releaseLock()
      }
    } catch (error: any) {
      // Clear timeout on error
      clearTimeout(timeoutId)

      // Handle abort - don't fire onError, caller detects via controller.signal.aborted
      if (error.name === 'AbortError') {
        return
      }

      // Re-throw other errors
      throw error
    }
  },

  // Complete with fallback models
  completeWithFallback: (data: {
    models: string[]
    messages: CompletionMessage[]
    max_cost?: number
    temperature?: number
    max_tokens?: number
    top_p?: number
  }) =>
    apiClient.post<CompletionResponse>('/llm/completions/complete_with_fallback/', data),

  // Estimate completion cost
  estimateCost: (data: {
    model_id: string
    prompt_tokens: number
    completion_tokens: number
  }) =>
    apiClient.post('/llm/completions/estimate_cost/', data),

  // Estimate batch cost for multiple models
  estimateBatchCost: (data: {
    model_ids: string[]
    prompt_text?: string
    typed_text?: string
    files_text?: string
    system_prompt?: string
    enable_mcp_tools?: boolean
    enable_reasoning?: boolean
    enable_file_tools?: boolean
    features_by_model?: Record<string, {
      system_prompt?: string
      enable_mcp_tools?: boolean
      enable_reasoning?: boolean
      enable_file_tools?: boolean
    }>
    estimated_completion_tokens?: number
    max_new_tokens?: number
    max_new_tokens_by_model?: Record<string, number>
    files?: Array<{ filename: string; mime?: string; size?: number }>
    images?: Array<{ mime?: string; size?: number; width?: number; height?: number }>
  }) =>
    apiClient.post('/llm/completions/estimate-batch-cost/', data),

  // Get rate limit info
  rateLimitInfo: (modelId: string) =>
    apiClient.get(`/llm/completions/rate_limit_info/`, {
      params: { model_id: modelId }
    }),

  // Get usage stats
  usageStats: () =>
    apiClient.get('/llm/completions/usage_stats/'),

  // Test connection with API key
  testConnection: (apiKey: string) =>
    apiClient.post('/llm/models/test-connection/', { api_key: apiKey }),

  // Refresh model catalog
  refreshModels: () =>
    apiClient.post('/llm/models/refresh/'),

  // Get precise generation usage from OpenRouter (for interrupted streams)
  // Backend retries with backoff (~26s max) since OpenRouter needs time to finalize data
  getGenerationUsage: async (generationId: string) => {
    const response = await apiClient.get(`/llm/generation/${generationId}/usage/`, {
      timeout: 35000,  // 35s to allow backend retries
    })
    return response.data as {
      usage: { prompt_tokens: number; completion_tokens: number; total_tokens: number }
      cost: number
      model: string
      generation_id: string
    }
  },
}
