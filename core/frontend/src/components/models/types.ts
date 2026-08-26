/**
 * Central type definitions for model comparison components
 * This file serves as the single source of truth for shared types
 */

// Re-export Model and WebSource from API (source of truth for API types)
import type { Model, WebSource, ToolCall, ToolResult, ToolExecution, ToolCallApproval } from '@/api/llm'
import type { SparkFramework, Spark } from '@/api/sparks'
import type { AssetReference } from '@/api/assets'
export type { Model, WebSource, ToolCall, ToolResult, ToolExecution, ToolCallApproval }

// Message content types for multimodal support
export type MessageContentPart =
  | { type: 'text'; text: string }
  | { type: 'image_url'; image_url: { url: string } }
  | { type: 'file'; file: { filename: string; file_data: string } }
  | { type: 'asset_ref'; asset_id: string; filename: string; mime_type: string; asset_type: string; width?: number; height?: number; download_url: string }

export type MessageContent = string | MessageContentPart[]

// Attachment interfaces for user messages
export interface ImageAttachment {
  id: string
  type: 'image'
  file: File
  preview: string
  base64?: string
  // Asset reference (populated after upload to backend)
  assetId?: string
  assetUrl?: string
}

export interface FileAttachment {
  id: string
  type: 'file'
  file: File
  base64?: string
  textContent?: string  // For text files (TXT, JSON, CSV, etc.) - content read and inserted into message
  // Asset reference (populated after upload to backend)
  assetId?: string
  assetUrl?: string
}

export interface VideoAttachment {
  id: string
  type: 'video'
  file: File
  preview: string      // blob URL for <video> element
  assetId?: string
  assetUrl?: string
}

export interface AudioAttachment {
  id: string
  type: 'audio'
  file: File
  preview: string      // blob URL for <audio> element
  assetId?: string
  assetUrl?: string
}

export type Attachment = ImageAttachment | FileAttachment | VideoAttachment | AudioAttachment

// A message attachment as reconstructed from persisted API history: the
// browser File object never survives a reload, so `file` carries only the
// metadata (name/type/size) every attachment preview actually reads —
// never the Blob-only members a freshly-composed Attachment.file has.
export interface ReconstructedAttachment {
  id: string
  type: 'image' | 'file' | 'video' | 'audio'
  file: { name: string; type: string; size: number }
  assetId: string
  assetUrl: string
  preview?: string
}

export type MessageAttachment = Attachment | ReconstructedAttachment

/** Called after a tool result is available (approval flow or execution), to continue the conversation with it. */
export type ToolExecutedHandler = (toolCallId: string, toolName: string, result: Record<string, unknown> | undefined) => void

/** A single-model cost estimate as displayed inline while composing a message (ChatPanel/MessageInput). */
export interface CostEstimate {
  cost?: number
  prompt_tokens?: number
  completion_tokens?: number
}

/**
 * The shape an attachment can actually have while a message is being
 * prepared for send: a freshly composed Attachment (real File), one
 * reconstructed from persisted API history (no File; already uploaded), or
 * one that crossed the new-conversation sessionStorage handoff (upload
 * in flight, failed, or done). Runtime code narrows by field presence —
 * `file instanceof File`, `assetId` set, `uploadFailed` — rather than a
 * discriminant, since that handoff can drop `file` and add
 * `fileName`/`fileType`/`fileSize`/`assetRef` interchangeably.
 */
export interface AttachmentLike {
  id: string
  type: 'image' | 'file' | 'video' | 'audio'
  file?: File | { name: string; type: string; size: number }
  base64?: string
  textContent?: string
  preview?: string
  assetId?: string
  assetUrl?: string
  assetRef?: AssetReference
  fileName?: string
  fileType?: string
  fileSize?: number
  uploadFailed?: boolean
}

// Message interface - used across chat components
export interface Message {
  role: 'user' | 'assistant' | 'tool'
  content: MessageContent
  timestamp: Date
  message_id?: string    // Unique ID for this message (used for file metadata tracking)
  tool_call_id?: string  // For role: 'tool' messages - matches the tool_call.id
  model?: string
  model_id?: string
  provider?: string
  provider_icon_slug?: string
  provider_icon_url?: string
  model_icon_slug?: string
  model_icon_url?: string
  cost?: number
  prompt_cost?: number
  completion_cost?: number
  latency?: number
  tokens?: {
    prompt: number
    completion: number
  }
  isError?: boolean
  // Machine-readable error code from the backend for actionable errors
  // ('no_api_key' | 'invalid_api_key' | 'insufficient_credits') — drives
  // direct-resolution UI (open API-key settings) instead of a dead end.
  errorCode?: string
  finish_reason?: string  // 'stop', 'length', 'content_filter', etc.
  isTruncated?: boolean   // Automatically set to true when finish_reason === 'length'
  isUnsupported?: boolean // True when the model doesn't support the features used in the message
  isInterrupted?: boolean // True when the stream was cancelled/interrupted by the user
  is_interrupted?: boolean // Alias for isInterrupted (snake_case from backend)
  is_stopped?: boolean    // True when user clicked Stop and partial content was preserved
  error?: string          // Error message when the response failed
  attachments?: MessageAttachment[] // Files and images attached to user messages
  reasoning_content?: string  // Full reasoning/thinking process from reasoning models
  is_reasoning?: boolean      // True while receiving reasoning chunks (streaming phase)
  pending_approvals?: ToolCallApproval[]   // MCP tool call approvals awaiting user decision
  tool_calls?: ToolCall[]        // Tool calls requested by the model (from finish_reason=tool_calls)
  file_tool_executions?: ToolExecution[]  // File tool executions with their results
  web_sources?: WebSource[]   // Web search sources/citations (URLs, titles, content)
  images?: string[]           // Generated images from image generation models (data URLs: "data:image/png;base64,...")

  // Sparks - interactive React components generated by AI
  sparks?: Array<
    Pick<Spark, 'id' | 'title' | 'framework' | 'code' | 'version' | 'is_ignited'> & {
      parent_id?: string | null  // ID of the parent spark (for version tracking)
    }
  >

  // Sterna routing info (when model was auto-routed)
  sterna_route?: {
    resolved_model: string
    resolved_model_name: string
    score: number
    tier: number
    reason: string
    cost_tier: string
  }

  // Steps-based structure for multi-step tool execution flow
  steps?: Array<
    | { type: 'text'; content: string }
    | { type: 'reasoning'; content: string; isStreaming: boolean }
    | {
        type: 'tool_executions';
        executions: ToolExecution[]
        isExecuting?: boolean    // True while any tool in this step is executing
      }
  >
}

// Filters interface - used for model filtering
export interface Filters {
  search?: string
  provider?: string
  maxPrice?: number
  minContext?: number
  supportsFunctions?: boolean
  supportsStructuredOutputs?: boolean
  supportsReasoning?: boolean
  supportsPromptCaching?: boolean
  supportsStreamCancellation?: boolean
  input_modalities?: string[]  // For vision, audio, etc. - consistent with backend
}

// Model parameters interface - used for configuring model behavior
export interface ModelParameters {
  // Basic parameters
  temperature: number
  max_tokens: number
  top_p: number

  // Additional sampling parameters
  top_k?: number
  frequency_penalty?: number
  presence_penalty?: number
  repetition_penalty?: number
  min_p?: number
  top_a?: number

  // Streaming & reasoning
  enable_streaming?: boolean
  enable_reasoning?: boolean
  reasoning_effort?: 'low' | 'medium' | 'high'  // For effort-based models (OpenAI o-series, Grok)
  reasoning_max_tokens?: number  // For token-limited models (Anthropic, Gemini, Qwen) - min 1024, max 32000

  // Web Search (Brave Search) - search with images, videos, places, news
  enable_brave_search?: boolean

  // MCP Tools
  enable_mcp_tools?: boolean

  // File Tools - enable AI assistants to manipulate files in /workspace
  enable_file_tools?: boolean

  // Image Generation - enable AI to generate images
  enable_image_generation?: boolean

  // Video Generation - enable AI to generate videos
  enable_video_generation?: boolean

  // Sparks - enable AI to generate interactive React components
  enable_sparks?: boolean

  // Knowledge Base - enable AI to query user's personal knowledge base
  enable_knowledge_base?: boolean

  // System prompt & memory
  system_prompt?: string
  chat_memory?: number  // Number of previous message pairs to include
}

// Spark definition for chat-level sparks
export interface ChatSpark {
  id: string
  title: string
  framework: SparkFramework
  code: string
  version?: number
  parent_id?: string | null  // ID of the parent spark (for version tracking)
}

/**
 * How chat instructions combine with global instructions
 */
export type ChatInstructionsMode = 'override' | 'append'

/**
 * Chat-specific custom instructions
 */
export interface ChatInstructions {
  content: string
  mode: ChatInstructionsMode  // 'override' replaces global, 'append' adds to global
}

// Chat interface - represents a single chat session
export interface Chat {
  id: string
  model: Model | null
  messages: Message[]
  isLoading: boolean
  parameters: ModelParameters
  disabled?: boolean
  hidden?: boolean  // If true, chat is not rendered (but preserved in data)
  sparks?: ChatSpark[]  // Sparks linked to this chat (may not be linked to specific messages)
  instructions?: ChatInstructions  // Chat-specific custom instructions
}

// ChatGroup interface - represents a group of chats (full conversation data)
export interface ChatGroup {
  id: string
  name: string
  createdAt: Date
  updatedAt: Date
  chats: Chat[]
  isCustomName?: boolean
  consigliereSessionId?: string
}

// ChatGroupSummary interface - for displaying in lists without full chat data
export interface ChatGroupSummary {
  id: string
  name: string
  fullName: string
  createdAt: Date
  updatedAt: Date
}
