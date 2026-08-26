/**
 * Request and response shapes exchanged over the streaming
 * (Server-Sent Events) completion endpoints — chat completion
 * requests/responses, usage accounting, and the coding-agent and
 * routing events carried inside a stream. OpenAPI describes a
 * request/response pair, not an event stream, so these payloads have
 * no corresponding schema operation for openapi-typescript to
 * generate from. Maintained by hand against the API.
 */

// Message content types for multimodal support (matches
// components/models/types.ts's MessageContentPart)
type MessageContentPart =
  | { type: 'text'; text: string }
  | { type: 'image_url'; image_url: { url: string } }
  | { type: 'file'; file: { filename: string; file_data: string } }
  | { type: 'asset_ref'; asset_id: string; filename: string; mime_type: string; asset_type: string; width?: number; height?: number; download_url: string }

export interface CompletionMessage {
  role: 'system' | 'user' | 'assistant' | 'tool'
  content: string | MessageContentPart[]  // Support both text-only and multimodal content
  tool_call_id?: string  // Required for 'tool' role messages
  tool_calls?: Array<{  // Present in 'assistant' messages that request tool calls
    id: string
    type: 'function'
    function: {
      name: string
      arguments: string
    }
  }>
}

export interface CompletionRequest {
  model: string
  messages: CompletionMessage[]
  temperature?: number
  max_tokens?: number
  top_p?: number
  stream?: boolean

  // Additional sampling parameters
  top_k?: number
  frequency_penalty?: number
  presence_penalty?: number
  repetition_penalty?: number
  min_p?: number
  top_a?: number

  // Reasoning parameters
  enable_reasoning?: boolean
  reasoning_effort?: 'low' | 'medium' | 'high'
  reasoning_max_tokens?: number  // For token-limited models (Anthropic, Gemini, Qwen) - min 1024, max 32000

  // Multimodal parameters - OpenRouter plugins for file processing
  // The file-parser plugin can handle PDFs, Office documents, and other file types
  plugins?: Array<{
    id: string
    pdf?: {
      engine: string
    }
    [key: string]: unknown  // Allow additional plugin configurations
  }>

  // MCP Tools integration
  enable_mcp_tools?: boolean

  // Brave Search integration - advanced search (images, videos, places, news)
  enable_brave_search?: boolean

  // File Tools integration - for AI assistants to manipulate files in /workspace
  // Note: Coding Agent is automatically enabled when file tools are enabled
  enable_file_tools?: boolean

  // Image Generation - enable AI to generate images via the generate_image tool
  enable_image_generation?: boolean

  // Video Generation - enable AI to generate videos via the generate_video tool
  enable_video_generation?: boolean

  // Sparks - enable AI to generate interactive components
  enable_sparks?: boolean

  // Knowledge Base - enable AI to query the user's personal knowledge base
  enable_knowledge_base?: boolean

  // Voice conversation mode - adjusts system prompt for voice output (no markdown, etc.)
  enable_voice_mode?: boolean

  // Custom system prompt (merged into the backend's built system prompt)
  system_prompt?: string

  conversation_id?: string
  chat_id?: string
  message_id?: string  // Message ID for file metadata tracking

  // Spark auto-fix request - triggers backend prompt injection
  spark_fix_request?: {
    spark_id: string
    spark_title: string
    error: string
  }

  // Spark ignite request - backend injects ignite (deploy) instructions into system prompt
  spark_ignite_request?: {
    spark_id: string
    spark_title: string
  }

  // Sterna routing override - force higher-tier model
  sterna_strength?: 'strong'

  // Asset-backed files to copy into the sandbox workspace (page reload / pre-upload,
  // when no File object is available). Backend resolves the asset IDs from R2.
  workspace_assets?: Array<{ asset_id: string; filename?: string }>
}

export interface CompletionUsage {
  prompt_tokens: number
  completion_tokens: number
  total_tokens: number
  estimated_cost?: number
}

export interface WebSource {
  url: string
  title?: string
}

// Coding Agent autonomous agent types
export interface CodingAgentStep {
  job_id: string
  step_index: number
  type: 'thinking' | 'tool_call' | 'tool_result' | 'text'
  tool?: string
  content?: string
  timestamp?: string
}

export interface CodingAgentQuestion {
  question: string
  options?: { label: string; description: string }[]
}

export interface CodingAgentResult {
  job_id: string
  success: boolean
  summary?: string
  files_modified?: string[]
  files_created?: string[]
  error?: string
  duration_ms: number
  total_tokens?: number
  steps?: CodingAgentStep[]
}

// Context compaction event data
export interface ContextCompactedData {
  original_messages: number
  compacted_messages: number
  original_tokens: number
  compacted_tokens: number
  tokens_saved: number
  compression_ratio: number
  duration_ms: number
}

// Sterna intelligent routing event data
export interface SternaRouteData {
  resolved_model: string
  resolved_model_name: string
  score: number
  tier: number
  reason: string
  cost_tier: string
}

export interface CompletionResponse {
  id: string
  model: string
  content: string
  finish_reason?: string
  usage?: CompletionUsage
  cost: number
  prompt_cost: number
  completion_cost: number
}
