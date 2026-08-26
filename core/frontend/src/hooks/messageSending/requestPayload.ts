import type { Model, ModelParameters } from '@/components/models/types'
import type { ApiMessage } from './types'

/** Spark auto-fix/ignite metadata and Sterna strength overrides accepted by sendToModel. */
export interface SendToModelOptions {
  sparkFixRequest?: {
    spark_id: string
    spark_title: string
    error: string
  }
  sparkIgniteRequest?: {
    spark_id: string
    spark_title: string
  }
  parameterOverrides?: Partial<ModelParameters>
  sternaStrength?: 'strong'
}

export interface BuildLLMRequestPayloadArgs {
  model: Model
  apiMessages: ApiMessage[]
  parameters: ModelParameters
  streamResponsesSetting: boolean
  hasFileAttachments: boolean
  voiceConversationActive: boolean
  options: SendToModelOptions | undefined
  activeGroupId: string
  chatId: string
  messageId: string
  workspaceAssets: { asset_id: string; filename: string }[]
}

/** Build the request body sent to the streaming completion endpoint. */
export function buildLLMRequestPayload(args: BuildLLMRequestPayloadArgs) {
  const {
    model, apiMessages, parameters, streamResponsesSetting, hasFileAttachments,
    voiceConversationActive, options, activeGroupId, chatId, messageId, workspaceAssets,
  } = args

  return {
    model: model.model_id,
    messages: apiMessages,
    temperature: parameters.temperature,
    max_tokens: parameters.max_tokens,
    top_p: parameters.top_p,
    stream: parameters.enable_streaming ?? streamResponsesSetting,
    // Additional sampling parameters - send all defined parameters even if 0
    // This ensures explicit control over model behavior
    ...(parameters.top_k !== undefined && { top_k: parameters.top_k }),
    ...(parameters.frequency_penalty !== undefined && { frequency_penalty: parameters.frequency_penalty }),
    ...(parameters.presence_penalty !== undefined && { presence_penalty: parameters.presence_penalty }),
    ...(parameters.repetition_penalty !== undefined && { repetition_penalty: parameters.repetition_penalty }),
    ...(parameters.min_p !== undefined && { min_p: parameters.min_p }),
    ...(parameters.top_a !== undefined && { top_a: parameters.top_a }),
    // Reasoning parameters - always send enable_reasoning to allow disabling
    ...(parameters.enable_reasoning !== undefined && { enable_reasoning: parameters.enable_reasoning }),
    ...(parameters.enable_reasoning && parameters.reasoning_effort && { reasoning_effort: parameters.reasoning_effort }),
    ...(parameters.enable_reasoning && parameters.reasoning_max_tokens && { reasoning_max_tokens: parameters.reasoning_max_tokens }),
    // Multimodal file processing - add OpenRouter plugins when files are attached
    // The file-parser plugin automatically handles PDFs, Office documents, and other file types
    ...(hasFileAttachments && {
      plugins: [
        { id: 'file-parser' }
      ]
    }),
    // MCP Tools integration
    ...(parameters.enable_mcp_tools !== undefined && { enable_mcp_tools: parameters.enable_mcp_tools }),
    // Brave Search integration - advanced search with images, videos, places, news
    ...(parameters.enable_brave_search !== undefined && { enable_brave_search: parameters.enable_brave_search }),
    // File Tools integration - enable AI assistants to manipulate files in /workspace
    ...(parameters.enable_file_tools !== undefined && { enable_file_tools: parameters.enable_file_tools }),
    // Image Generation - enable AI to generate images using the generate_image tool
    ...(parameters.enable_image_generation !== undefined && { enable_image_generation: parameters.enable_image_generation }),
    // Video Generation - enable AI to generate videos using the generate_video tool
    ...(parameters.enable_video_generation !== undefined && { enable_video_generation: parameters.enable_video_generation }),
    // Sparks - enable AI to generate interactive React components
    ...(parameters.enable_sparks !== undefined && { enable_sparks: parameters.enable_sparks }),
    // Knowledge Base - enable AI to query user's personal knowledge base
    ...(parameters.enable_knowledge_base !== undefined && { enable_knowledge_base: parameters.enable_knowledge_base }),
    // Conversation context - always send for chat instructions and sandbox isolation
    conversation_id: activeGroupId, // Use group ID as conversation ID
    chat_id: chatId, // Use chat ID for chat instructions and sandbox isolation
    // Message ID for file metadata tracking (only when tools are enabled)
    ...((parameters.enable_file_tools || parameters.enable_image_generation || parameters.enable_video_generation || parameters.enable_sparks || parameters.enable_knowledge_base) && {
      message_id: messageId, // Pass message ID for file metadata tracking
    }),
    // Voice conversation mode - adjusts system prompt for voice output (no markdown, etc.)
    ...(voiceConversationActive && { enable_voice_mode: true }),
    // Spark auto-fix request - backend injects fix instructions into system prompt
    ...(options?.sparkFixRequest && { spark_fix_request: options.sparkFixRequest }),
    // Spark ignite request - backend injects ignite instructions into system prompt
    ...(options?.sparkIgniteRequest && { spark_ignite_request: options.sparkIgniteRequest }),
    // Sterna strength override - force higher-tier model selection
    ...(options?.sternaStrength && { sterna_strength: options.sternaStrength }),
    // Asset-backed files for workspace copy (page reload / pre-upload, no File object available)
    ...(workspaceAssets.length > 0 && { workspace_assets: workspaceAssets }),
  }
}
