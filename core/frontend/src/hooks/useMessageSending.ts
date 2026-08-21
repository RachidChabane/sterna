/**
 * useMessageSending Hook
 *
 * Manages message sending operations:
 * - Send messages to LLM models
 * - Handle streaming responses
 * - Process tool calls
 * - Handle reasoning and web search results
 * - Manage attachments and modalities
 */

import { useRef, useCallback, useState } from 'react'
import type { Chat, Model, Message, MessageContentPart, Attachment, ImageAttachment, FileAttachment, VideoAttachment, AudioAttachment, ModelParameters } from '@/components/models/types'
import { llmApi, type CodingAgentStep, type CodingAgentResult, type CodingAgentQuestion, type ContextCompactedData } from '@/api/llm'
import { extractTextFromContent } from '@/utils/chatUtils'
import { extractSparks } from '@/utils/sparkParser'
import { DEFAULT_PARAMETERS } from '@/components/models/constants'
import { getUserFriendlyErrorMessage } from '@/utils/errorMessages'
import { isPDFFile, isOfficeFile, formatFileSize } from '@/utils/fileUtils'
import { useActiveConversationStore } from '@/store/activeConversationStore'
import { useSettingsStore } from '@/store/settingsStore'
import useModelStore from '@/store/modelStore'
import { useUsageQuotaStore } from '@/store/usageQuotaStore'
import { conversationsAPI } from '@/api/conversations'
import { assetsAPI, assetToReference, getAssetTypeFromMime, type AssetReference } from '@/api/assets'
import { sparksAPI } from '@/api/sparks'
import { useArtifactsPanelStore } from '@/store/artifactsPanelStore'
import { codeSessionApi } from '@/api/codeSession'
import { useProjectPanelStore } from '@/store/projectPanelStore'

// Tools that use the Coding Agent display (progress steps, "Open IDE" button)
const CODING_AGENT_TOOLS = new Set(['coding_agent', 'plan_implementation', 'implement_plan', 'edit_plan'])

// API message type that includes system role (not stored in UI state)
type ApiMessage = {
  role: 'user' | 'assistant' | 'tool' | 'system'
  content: any
  tool_call_id?: string
}

/**
 * Build a dynamic message for unsupported attachment types
 * @returns Message string or null if all attachments are supported
 */
function buildUnsupportedAttachmentsMessage(
  hasImages: boolean,
  hasPDFs: boolean,
  hasOfficeFiles: boolean,
  hasText: boolean,
  supportsVision: boolean,
  supportsFiles: boolean
): string | null {
  const unsupportedTypes: string[] = []

  if (hasImages && !supportsVision) {
    unsupportedTypes.push('image')
  }
  if ((hasPDFs || hasOfficeFiles) && !supportsFiles) {
    // If both PDFs and Office files, use generic term
    if (hasPDFs && hasOfficeFiles) {
      unsupportedTypes.push('document file')
    } else if (hasPDFs) {
      unsupportedTypes.push('PDF file')
    } else {
      unsupportedTypes.push('Office document')
    }
  }

  // No unsupported types
  if (unsupportedTypes.length === 0) return null

  // Build first part: what's unsupported
  let typesText: string
  if (unsupportedTypes.length === 1) {
    typesText = `${unsupportedTypes[0]} inputs`
  } else {
    const last = unsupportedTypes.pop()!
    typesText = `${unsupportedTypes.join(', ')} and ${last} inputs`
  }

  // Build second part: what will be processed
  const supportedParts: string[] = []

  if (hasText) {
    supportedParts.push('text')
  }
  if (hasImages && supportsVision) {
    supportedParts.push('images')
  }
  if ((hasPDFs || hasOfficeFiles) && supportsFiles) {
    // If both PDFs and Office files, use generic term
    if (hasPDFs && hasOfficeFiles) {
      supportedParts.push('document files')
    } else if (hasPDFs) {
      supportedParts.push('PDF files')
    } else {
      supportedParts.push('Office documents')
    }
  }

  // If nothing is supported, return a different message
  if (supportedParts.length === 0) {
    return `This model does not support ${typesText}. Your message cannot be processed.`
  }

  // Build the "only X will be processed" part
  let processingText: string
  if (supportedParts.length === 1) {
    processingText = `Only the ${supportedParts[0]}`
  } else if (supportedParts.length === 2) {
    processingText = `Only the ${supportedParts[0]} and ${supportedParts[1]}`
  } else {
    const last = supportedParts.pop()!
    processingText = `Only the ${supportedParts.join(', ')}, and ${last}`
  }

  return `This model does not support ${typesText}. ${processingText} will be processed.`
}

/**
 * Upload attachments as assets and return enriched attachments with asset references
 * This persists files to R2/PostgreSQL for permanent storage
 *
 * Note: If an attachment already has an `assetRef` (e.g., from pre-upload in new conversation flow),
 * it will be used directly without re-uploading.
 */
async function uploadAttachmentsAsAssets(
  chatId: string,
  attachments: Attachment[]
): Promise<{ enriched: Attachment[], assetRefs: AssetReference[] }> {
  if (attachments.length === 0) {
    return { enriched: [], assetRefs: [] }
  }

  const enriched: Attachment[] = []
  const assetRefs: AssetReference[] = []

  // Upload each attachment in parallel
  const uploadPromises = attachments.map(async (att) => {
    // Check if attachment already has an asset reference (from pre-upload)
    const existingAssetRef = (att as any).assetRef as AssetReference | undefined
    if (existingAssetRef && existingAssetRef.asset_id) {
      
      return {
        enriched: att,
        assetRef: existingAssetRef,
      }
    }

    // Check if attachment has assetId but no full assetRef (legacy format)
    const existingAssetId = (att as any).assetId as string | undefined
    if (existingAssetId) {
      
      // Build a minimal asset reference from available data
      const assetRef: AssetReference = {
        type: 'asset_ref',
        asset_id: existingAssetId,
        filename: (att as any).fileName || att.file?.name || 'unknown',
        mime_type: (att as any).fileType || att.file?.type || 'application/octet-stream',
        asset_type: att.type === 'image' ? 'image' : 'generated',
        size_bytes: (att as any).fileSize || att.file?.size || 0,
        download_url: (att as any).assetUrl || `/api/workspaces/assets/${existingAssetId}/download/`,
      }
      return {
        enriched: att,
        assetRef,
      }
    }

    // No existing asset - need to upload
    // Check if we have a valid File object
    if (!att.file || !(att.file instanceof File)) {
      console.warn(`[uploadAttachmentsAsAssets] No File object for attachment, skipping upload`)
      return { enriched: att, assetRef: null }
    }

    try {
      const result = await assetsAPI.uploadFile(chatId, att.file, {
        assetType: att.type === 'image' ? 'image' : getAssetTypeFromMime(att.file.type),
      })

      if (result.success && result.asset) {
        // Mutate original attachment to add assetId/assetUrl
        // This ensures the message attachments (which reference the same objects) get updated
        ;(att as any).assetId = result.asset.id
        ;(att as any).assetUrl = result.asset.download_url

        // Enrich attachment with asset reference
        const enrichedAtt = {
          ...att,
          assetId: result.asset.id,
          assetUrl: result.asset.download_url,
        }
        return {
          enriched: enrichedAtt,
          assetRef: assetToReference(result.asset),
        }
      } else {
        console.warn(`[uploadAttachmentsAsAssets] Failed to upload ${att.file?.name || 'unknown'}:`, result.error)
        // Return original attachment without asset reference
        return { enriched: att, assetRef: null }
      }
    } catch (error) {
      console.error(`[uploadAttachmentsAsAssets] Error uploading ${att.file?.name || 'unknown'}:`, error)
      return { enriched: att, assetRef: null }
    }
  })

  const results = await Promise.all(uploadPromises)

  for (const result of results) {
    enriched.push(result.enriched)
    if (result.assetRef) {
      assetRefs.push(result.assetRef)
    }
  }

  
  return { enriched, assetRefs }
}

interface UseMessageSendingProps {
  chats: Chat[]
  activeGroupId: string
  chatGroups: any[]
  setChatGroups: React.Dispatch<React.SetStateAction<any[]>>
  attachments: Attachment[]
  setAttachments: React.Dispatch<React.SetStateAction<Attachment[]>>
  toast: (options: any) => void
  isAuthenticated: boolean
  openModal: (variant: string, returnPath: string) => void
  getAuthModalVariant: () => string
}

/** Options for sendToModel */
interface SendToModelOptions {
  /** Spark auto-fix request metadata */
  sparkFixRequest?: {
    spark_id: string
    spark_title: string
    error: string
  }
  /** Spark ignite request metadata */
  sparkIgniteRequest?: {
    spark_id: string
    spark_title: string
  }
  /** Override specific parameters for this request */
  parameterOverrides?: Partial<ModelParameters>
  /** Sterna strength override ('strong' forces higher-tier model) */
  sternaStrength?: 'strong'
}

interface UseMessageSendingReturn {
  sendToModel: (chatId: string, model: Model, messages: Message[], options?: SendToModelOptions) => Promise<void>
  composeAndSend: (targetChatIds: string[], content: string, localAttachments: Attachment[], isToolContinuation?: boolean) => Promise<void>
  sendMessage: (content: string) => void
  sendSparkFixMessage: (chatId: string, content: string, sparkFixRequest: { spark_id: string; spark_title: string; error: string }) => Promise<void>
  sendIgniteMessage: (chatId: string, sparkIgniteRequest: { spark_id: string; spark_title: string }) => Promise<void>
  abortControllersRef: React.MutableRefObject<Map<string, AbortController>>
  pendingCodingAgentQuestion: CodingAgentQuestion | null
  answerCodingAgentQuestion: (chatId: string, answer: string) => void
}

export function useMessageSending({
  chats,
  activeGroupId,
  chatGroups,
  setChatGroups,
  attachments,
  setAttachments,
  toast,
  isAuthenticated,
  openModal,
  getAuthModalVariant,
}: UseMessageSendingProps): UseMessageSendingReturn {
  // Track abort controllers for each chat to allow request cancellation
  const abortControllersRef = useRef<Map<string, AbortController>>(new Map())

  // Pending coding agent question state (for ask_user MCP tool)
  const pendingCodingAgentQuestionRef = useRef<CodingAgentQuestion | null>(null)
  const [pendingQuestionVersion, setPendingQuestionVersion] = useState(0)

  // Get streaming preference from settings (used as fallback if not specified in parameters)
  const streamResponsesSetting = useSettingsStore((state) => state.chat.streamResponses)

  // Get voice conversation mode from settings (adjusts system prompt for voice output)
  const voiceConversationActive = useSettingsStore((state) => state.voiceConversationActive)

  // Get addRecentChatModel to track model usage when messages are sent
  const addRecentChatModel = useModelStore((state) => state.addRecentChatModel)

  // Get quota refresh function to update usage display after message sends
  const refreshQuotaAfterUsage = useUsageQuotaStore((state) => state.refreshAfterUsage)

  const sendToModel = useCallback(async (
    chatId: string,
    model: Model,
    messages: Message[],
    options?: SendToModelOptions
  ) => {
    // Get chat parameters
    const chat = chats.find(c => c.id === chatId)
    const chatParameters = chat?.parameters || DEFAULT_PARAMETERS
    // Apply any parameter overrides (e.g., force enable_sparks for fix requests)
    const baseParameters = options?.parameterOverrides
      ? { ...chatParameters, ...options.parameterOverrides }
      : chatParameters

    // Auto-detect @knowledge mention in the latest user message and enable knowledge base
    const lastUserMessage = [...messages].reverse().find(m => m.role === 'user')
    const messageContent = typeof lastUserMessage?.content === 'string'
      ? lastUserMessage.content
      : Array.isArray(lastUserMessage?.content)
        ? lastUserMessage.content.find((c): c is Extract<MessageContentPart, { type: 'text' }> => c.type === 'text')?.text || ''
        : ''
    const hasKnowledgeMention = /@knowledge\b/i.test(messageContent)

    // Merge parameters with auto-detected knowledge base flag
    const parameters = hasKnowledgeMention
      ? { ...baseParameters, enable_knowledge_base: true }
      : baseParameters

    // Set loading state using functional update
    setChatGroups(prevGroups =>
      prevGroups.map((group: any) =>
        group.id === activeGroupId
          ? {
              ...group,
              chats: group.chats.map((c: Chat) =>
                c.id === chatId ? { ...c, isLoading: true } : c
              )
            }
          : group
      )
    )

    const startTime = Date.now()

    // Generate a unique ID for this message (for file metadata tracking)
    // Using timestamp-based UUID to ensure uniqueness across all messages
    const messageId = `msg_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`

    // Apply chat memory: limit to last N message pairs (user + assistant)
    const chatMemory = parameters.chat_memory ?? 8
    let limitedMessages = messages
    if (messages.length > chatMemory * 2) {
      // Keep the last N pairs of messages
      limitedMessages = messages.slice(-chatMemory * 2)
    }

    // Prepare messages with optional system prompt
    // Filter out UI-only messages (errors, unsupported warnings) before sending to API
    // Note: Keep interrupted messages as they contain partial valid responses
    const filteredMessages = limitedMessages.filter(m => !m.isError && !m.isUnsupported)
    let apiMessages: ApiMessage[] = filteredMessages.map(m => ({
      role: m.role,
      content: m.content,
      ...(m.tool_call_id ? { tool_call_id: m.tool_call_id } : {}),  // Include tool_call_id for tool messages
    }))

    

    // Add system prompt if provided
    // Note: System prompt combination (web search, MCP tools, etc.) is handled by the backend
    if (parameters.system_prompt && parameters.system_prompt.trim()) {
      apiMessages = [
        { role: 'system' as const, content: parameters.system_prompt },
        ...apiMessages
      ]
    }

    // Build API messages by incorporating attachments (images/PDFs) and text-file contents for the last user message,
    // filtering parts based on the target model's supported modalities
    // IMPORTANT: Find index in apiMessages (not limitedMessages) since filteredMessages may have removed some
    const lastApiUserIndex = [...apiMessages].map((m, i) => ({ m, i })).reverse().find(x => x.m.role === 'user')?.i
    // Also find the corresponding state message (from limitedMessages) to get attachments
    const lastStateUserMsg = [...limitedMessages].reverse().find(m => m.role === 'user' && !m.isError && !m.isUnsupported)
    let hasFileAttachments = false
    let uploadedFiles: File[] = []  // Extract File objects for file tools
    let workspaceAssets: { asset_id: string; filename: string }[] = []  // Asset-backed files for workspace copy
    if (lastApiUserIndex !== undefined && lastStateUserMsg) {
      const lastUserStateMsg = lastStateUserMsg
      const attachments = (lastUserStateMsg as any).attachments || []

      // Helper function to convert blob to data URL
      const blobToDataUrl = async (blob: Blob): Promise<string> => {
        return new Promise((resolve, reject) => {
          const reader = new FileReader()
          reader.onloadend = () => resolve(reader.result as string)
          reader.onerror = reject
          reader.readAsDataURL(blob)
        })
      }

      // Fetch base64 for images/files that only have assetId or assetRef (no base64 data)
      // This handles:
      // 1. Images loaded from DB after page reload (have assetId)
      // 2. Images pre-uploaded in new conversation flow (have assetRef.asset_id)
      
      for (const att of attachments) {
        // Get asset ID from either assetId or assetRef.asset_id
        const assetId = att.assetId || att.assetRef?.asset_id
        

        if (att.type === 'image' && !att.base64 && assetId) {
          try {
            
            const blob = await assetsAPI.download(assetId)
            if (blob) {
              att.base64 = await blobToDataUrl(blob)
              
            }
          } catch (error) {
            console.error(`[sendToModel] Failed to fetch image for assetId ${assetId}:`, error)
          }
        }
        // Also handle PDFs/files that only have assetId or assetRef
        if (att.type === 'file' && !att.base64 && assetId && !att.textContent) {
          try {
            
            const blob = await assetsAPI.download(assetId)
            if (blob) {
              att.base64 = await blobToDataUrl(blob)
              
            }
          } catch (error) {
            console.error(`[sendToModel] Failed to fetch file for assetId ${assetId}:`, error)
          }
        }
      }

      // Helper to check if attachment is a PDF (handles both File object and extracted properties)
      const isPDF = (a: any): boolean => {
        if (a.file && isPDFFile(a.file)) return true
        // Fallback: check extracted properties or assetRef
        const filename = a.fileName || a.file?.name || a.assetRef?.filename || ''
        const mimeType = a.fileType || a.file?.type || a.assetRef?.mime_type || ''
        return mimeType === 'application/pdf' || filename.toLowerCase().endsWith('.pdf')
      }

      // Helper to check if attachment is an Office file
      const isOffice = (a: any): boolean => {
        if (a.file && isOfficeFile(a.file)) return true
        // Fallback: check extracted properties or assetRef
        const filename = a.fileName || a.file?.name || a.assetRef?.filename || ''
        const mimeType = a.fileType || a.file?.type || a.assetRef?.mime_type || ''
        const officeExtensions = ['.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.odt', '.ods', '.odp']
        const officeMimes = [
          'application/msword',
          'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
          'application/vnd.ms-excel',
          'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
          'application/vnd.ms-powerpoint',
          'application/vnd.openxmlformats-officedocument.presentationml.presentation',
        ]
        return officeMimes.includes(mimeType) || officeExtensions.some(ext => filename.toLowerCase().endsWith(ext))
      }

      const imageAtts = attachments.filter((a: any) => a.type === 'image' && a.base64)
      const pdfAtts = attachments.filter((a: any) => a.type === 'file' && a.base64 && !a.textContent && isPDF(a))
      const officeAtts = attachments.filter((a: any) => a.type === 'file' && a.base64 && !a.textContent && isOffice(a))
      const otherBinaryAtts = attachments.filter((a: any) => a.type === 'file' && a.base64 && !a.textContent && !isPDF(a) && !isOffice(a))
      const textFileAtts = attachments.filter((a: any) => a.type === 'file' && a.textContent)
      const videoAtts = attachments.filter((a: any) => a.type === 'video')
      const audioAtts = attachments.filter((a: any) => a.type === 'audio')
      const mediaToolAtts = [...videoAtts, ...audioAtts]

      

      // Extract File objects for file tools (workspace upload)
      // This includes ALL file attachments (PDFs, text files, video, audio) for workspace access
      const allFileAtts = attachments.filter((a: any) =>
        (a.type === 'file' && a.file) ||
        (a.type === 'video' && a.file) ||
        (a.type === 'audio' && a.file)
      )
      uploadedFiles = allFileAtts.map((a: any) => a.file).filter((f: any) => f instanceof File)

      // Collect asset IDs for workspace upload — only for assets WITHOUT a real File object
      // (assets with real File objects are sent via FormData and copied by the request.FILES path)
      workspaceAssets = attachments
        .filter((a: any) => {
          const assetId = a.assetId || a.assetRef?.asset_id
          const hasRealFile = a.file instanceof File
          return assetId && !hasRealFile && (a.type === 'file' || a.type === 'video' || a.type === 'audio')
        })
        .map((a: any) => ({
          asset_id: a.assetId || a.assetRef?.asset_id,
          filename: a.fileName || a.assetRef?.filename || 'unknown',
        }))

      // Model capabilities
      const supportsVision = model.input_modalities?.includes('image')
      const supportsFiles = model.input_modalities?.includes('file')
      

      // Only include attachments supported by the target model
      const includeImages = supportsVision ? imageAtts : []
      const includePDFs = supportsFiles ? pdfAtts : []
      const includeOfficeFiles = supportsFiles ? officeAtts : []
      const includeOtherBinaryFiles = supportsFiles ? otherBinaryAtts : []
      const allIncludeFiles = [...includePDFs, ...includeOfficeFiles, ...includeOtherBinaryFiles]
      hasFileAttachments = allIncludeFiles.length > 0

      // Debug: Log what images will actually be included
      

      // Extract original typed text from the message content
      const originalText = extractTextFromContent(lastUserStateMsg.content as any)

      // Append text file contents for API only
      let apiText = originalText
      if (textFileAtts.length > 0) {
        for (const file of textFileAtts) {
          // Handle both normal attachments (file.file.name) and serialized ones (file.fileName)
          const fileName = file.file?.name || (file as any).fileName || 'file'
          apiText += `\n\n--- Fichier attaché: ${fileName} ---\n${file.textContent}\n--- Fin du fichier ---`
        }
      }

      // Build media text references for video/audio (lightweight URL references, not base64)
      const buildMediaTextRef = (text: string): string => {
        if (mediaToolAtts.length === 0) return text
        const lines = mediaToolAtts.map((media: any) => {
          const filename = media.fileName || media.file?.name || media.assetRef?.filename
          const assetId = media.assetId || media.assetRef?.asset_id
          const assetUrl = media.assetUrl || media.assetRef?.download_url
            || (assetId ? `/api/workspaces/assets/${assetId}/download/` : '')
          const mime = media.fileType || media.file?.type || media.assetRef?.mime_type || ''
          const size = media.fileSize || media.file?.size || media.assetRef?.size_bytes || 0
          const sizeStr = size > 0 ? `, ${formatFileSize(size)}` : ''
          return assetUrl ? `- ${filename}: asset_url="${assetUrl}" (${mime}${sizeStr})` : null
        }).filter(Boolean)

        if (lines.length > 0) {
          text += `\n\n[Attached media files (use asset_url with video tools like animate_image, animate_character):\n${lines.join('\n')}\n]`
        }
        return text
      }

      // Reconstruct the last user message content for API
      // Note: OpenRouter's file-parser plugin expects files (PDFs, Office docs) in the same format as images
      // Using image_url with the data URI scheme allows the plugin to detect and parse the file type
      if (includeImages.length > 0 || allIncludeFiles.length > 0) {
        // Build image metadata text for edit_image tool support
        // This lets the LLM know the asset_url to use when editing user-uploaded images
        let textWithImageMetadata = apiText
        if (includeImages.length > 0) {
          const imageMetadataLines = includeImages.map((img: any, idx: number) => {
            const filename = img.fileName || img.file?.name || img.assetRef?.filename || `image_${idx + 1}`
            // Get asset URL from various sources, or construct from asset ID
            const assetId = img.assetId || img.assetRef?.asset_id
            const assetUrl = img.assetUrl || img.assetRef?.download_url || (assetId ? `/api/workspaces/assets/${assetId}/download/` : '')
            return assetUrl ? `- ${filename}: asset_url="${assetUrl}"` : `- ${filename}`
          }).filter((line: string) => line.includes('asset_url'))

          if (imageMetadataLines.length > 0) {
            textWithImageMetadata += `\n\n[Attached images (for use with edit_image tool):\n${imageMetadataLines.join('\n')}\n]`
          }
        }

        // Append media (video/audio) text references
        textWithImageMetadata = buildMediaTextRef(textWithImageMetadata)

        const parts = [
          { type: 'text' as const, text: textWithImageMetadata },
          ...includeImages.map((img: any) => ({ type: 'image_url' as const, image_url: { url: img.base64 } })),
          ...allIncludeFiles.map((f: any) => ({ type: 'image_url' as const, image_url: { url: f.base64 } })),
        ]
        apiMessages[lastApiUserIndex] = { role: 'user', content: parts }

        // Debug: Log detailed base64 info
        const imageUrlPart = parts.find(p => p.type === 'image_url') as any
        const base64Value = imageUrlPart?.image_url?.url

      } else {
        // Append media (video/audio) text references even when no images/files
        apiMessages[lastApiUserIndex] = { role: 'user', content: buildMediaTextRef(apiText) }

      }

      // If after filtering nothing is left to send (no text and no supported parts), cancel early
      const hasTextToSend = (apiText || '').trim().length > 0
      const hasPartsToSend = includeImages.length > 0 || allIncludeFiles.length > 0
      const hasMediaRefs = mediaToolAtts.length > 0
      if (!hasTextToSend && !hasPartsToSend && !hasMediaRefs) {
        // No supported content; stop loading and bail out quickly
        setChatGroups(prev => prev.map((g: any) => g.id === activeGroupId ? {
          ...g,
          chats: g.chats.map((c: Chat) => c.id === chatId ? { ...c, isLoading: false } : c),
          updatedAt: new Date(),
        } : g))
        return
      }
    }

    const requestPayload = {
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
          {
            id: 'file-parser'
          }
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
      conversation_id: activeGroupId,  // Use group ID as conversation ID
      chat_id: chatId,  // Use chat ID for chat instructions and sandbox isolation
      // Message ID for file metadata tracking (only when tools are enabled)
      ...((parameters.enable_file_tools || parameters.enable_image_generation || parameters.enable_video_generation || parameters.enable_sparks || parameters.enable_knowledge_base) && {
        message_id: messageId,  // Pass message ID for file metadata tracking
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

    // Streaming state - declared OUTSIDE the try block because the catch block
    // (abort persistence path) reads these; declaring them inside the try would
    // throw a ReferenceError at runtime when the catch runs.
    let accumulatedContent = ''
    let totalContentForPersistence = '' // Never reset - used for final persistence
    let accumulatedReasoning = '' // Full reasoning content (accumulates progressively)
    let previousReasoningContent = '' // Content of previous reasoning steps (for delta calculation)
    let accumulatedWebSources: any[] = [] // Web search sources
    let allToolExecutions: any[] = [] // All tool executions for persistence (tracks across all tool calls)
    let accumulatedSparksFromTools: any[] = [] // Sparks created via create_spark tool (persisted by backend)
    let accumulatedSteps: any[] = [] // Track interleaved steps (text, reasoning, tool_executions) for proper persistence
    let currentTextStepStartIndex = 0 // Track where the current text step's content starts in accumulatedContent

    // Helper to extract only the new reasoning content (handles both delta and full content APIs)
    const getReasoningDelta = (current: string, previous: string): string => {
      if (!previous) return current
      // If current starts with previous content, it's accumulated - extract delta
      if (current.startsWith(previous)) {
        return current.slice(previous.length)
      }
      // Otherwise return full current (model sent fresh content)
      return current
    }
    let accumulatedImages: string[] = [] // Generated images from image generation models
    let accumulatedCodingAgentSteps: CodingAgentStep[] = [] // Coding Agent agent execution steps
    let accumulatedCodingAgentResult: CodingAgentResult | null = null // Coding Agent final result
    let sternaRouteData: any = null // Sterna routing info (auto-router resolved model)
    let streamingMessageTimestamp = new Date()
    let messageMetadata: any = null // Metadata from onDone (cost, usage, etc.)
    // Initialized via `null as ...` so TS keeps the full union type here: the value is only
    // assigned inside stream callbacks, which TS's control flow analysis does not track
    // (a plain `= null` initializer would narrow later reads to `never` after truthy checks).
    let lastUsageUpdate = null as {
      usage: { prompt_tokens: number; completion_tokens: number; total_tokens: number }
      cost: number
      prompt_cost: number
      completion_cost: number
      generation_id?: string
      generation_ids?: string[]
    } | null
    let generationId: string | null = null  // OpenRouter generation ID for precise usage after abort
    let generationIds: string[] = []  // All generation IDs across iterations for comprehensive billing

    // Use streaming for real-time responses
    try {
      // Create and store controller for this chat to allow cancellation
      const controller = new AbortController()
      abortControllersRef.current.set(chatId, controller)

      // Log uploaded files for debugging
      if (uploadedFiles.length > 0) {
        
      }

      await llmApi.completeStream(requestPayload, {
        onContent: (content: string) => {
          // Accumulate content as it streams in (keep same message throughout)
          accumulatedContent += content
          totalContentForPersistence += content // Also track for persistence (never reset)

          // Get the content for the current text step (from currentTextStepStartIndex to end)
          const currentTextStepContent = accumulatedContent.slice(currentTextStepStartIndex)

          // Update accumulatedSteps for persistence - track the interleaved structure
          const lastAccStep = accumulatedSteps[accumulatedSteps.length - 1]
          if (lastAccStep?.type === 'text') {
            // Update existing text step
            lastAccStep.content = currentTextStepContent
          } else {
            // Create new text step (first text or after tool_executions)
            accumulatedSteps.push({ type: 'text', content: currentTextStepContent })
          }

          // Update the message in real-time using steps structure
          setChatGroups(prevGroups =>
            prevGroups.map((group: any) => {
              if (group.id !== activeGroupId) return group

              return {
                ...group,
                chats: group.chats.map((c: Chat) => {
                  if (c.id !== chatId) return c

                  // Check if we already have a streaming message
                  const hasStreamingMessage = c.messages.some((m: Message) =>
                    m.role === 'assistant' && m.timestamp === streamingMessageTimestamp
                  )

                  if (hasStreamingMessage) {
                    // Update existing streaming message
                    return {
                      ...c,
                      messages: c.messages.map((m: Message) => {
                        if (m.timestamp !== streamingMessageTimestamp) return m

                        // Build steps: reasoning -> text -> tools -> text -> tools -> ...
                        const steps = m.steps || []
                        const lastStep = steps[steps.length - 1]

                        // If there was reasoning and now content is coming, finalize the reasoning step
                        if (lastStep?.type === 'reasoning') {
                          // Track this reasoning content so next reasoning step only shows new content
                          previousReasoningContent = accumulatedReasoning
                          return {
                            ...m,
                            content: accumulatedContent,
                            steps: [
                              ...steps.slice(0, -1),
                              { type: 'reasoning' as const, content: lastStep.content, isStreaming: false },
                              { type: 'text' as const, content: currentTextStepContent }
                            ],
                            reasoning_content: accumulatedReasoning || m.reasoning_content,
                            is_reasoning: false
                          }
                        }
                        // If last step is text, update it; otherwise create new text step
                        else if (lastStep?.type === 'text') {
                          return {
                            ...m,
                            content: accumulatedContent,
                            steps: [
                              ...steps.slice(0, -1),
                              { type: 'text' as const, content: currentTextStepContent }
                            ],
                            reasoning_content: accumulatedReasoning || m.reasoning_content,
                            is_reasoning: false
                          }
                        } else {
                          // Creating new text step after tool_executions (text only for this step)
                          return {
                            ...m,
                            content: accumulatedContent,
                            steps: [
                              ...steps,
                              { type: 'text' as const, content: currentTextStepContent }
                            ],
                            reasoning_content: accumulatedReasoning || m.reasoning_content,
                            is_reasoning: false
                          }
                        }
                      })
                    }
                  } else {
                    // Create new streaming message and set isLoading to false (streaming has started)
                    const streamingMessage: Message = {
                      role: 'assistant',
                      content: accumulatedContent,
                      timestamp: streamingMessageTimestamp,
                      model: model.name,
                      model_id: model.model_id,
                      provider: model.provider,
                      provider_icon_slug: model.provider_icon_slug,
                      provider_icon_url: model.provider_icon_url,
                      model_icon_slug: model.model_icon_slug,
                      model_icon_url: model.model_icon_url,
                      steps: [{ type: 'text' as const, content: currentTextStepContent }],
                      message_id: messageId  // Store message ID for file metadata tracking
                    }
                    return {
                      ...c,
                      messages: [...c.messages, streamingMessage],
                      isLoading: false  // Stop showing "Thinking..." once streaming starts
                    }
                  }
                })
              }
            })
          )
        },

        onReasoning: (content: string) => {
          // Accumulate reasoning progressively (like normal content)
          accumulatedReasoning += content

          // Update the message with accumulated reasoning in real-time using steps structure
          setChatGroups(prevGroups =>
            prevGroups.map((group: any) => {
              if (group.id !== activeGroupId) return group

              return {
                ...group,
                chats: group.chats.map((c: Chat) => {
                  if (c.id !== chatId) return c

                  // Check if we already have a streaming message
                  const hasStreamingMessage = c.messages.some((m: Message) =>
                    m.role === 'assistant' && m.timestamp === streamingMessageTimestamp
                  )

                  if (hasStreamingMessage) {
                    // Update existing message with reasoning step
                    return {
                      ...c,
                      messages: c.messages.map((m: Message) => {
                        if (m.timestamp !== streamingMessageTimestamp) return m

                        // Build steps: if last step is reasoning, update it; otherwise create new reasoning step
                        const steps = m.steps || []
                        const lastStep = steps[steps.length - 1]

                        if (lastStep?.type === 'reasoning') {
                          // Update existing reasoning step - extract delta from previous content
                          const reasoningDelta = getReasoningDelta(accumulatedReasoning, previousReasoningContent)
                          return {
                            ...m,
                            content: accumulatedReasoning,
                            reasoning_content: accumulatedReasoning,
                            is_reasoning: true,
                            steps: [
                              ...steps.slice(0, -1),
                              { type: 'reasoning' as const, content: reasoningDelta, isStreaming: true }
                            ]
                          }
                        } else {
                          // Reasoning arrived after a non-reasoning step.
                          // Check if there's a tool_executions step between the last reasoning and now.
                          // If not (just text), merge into the existing reasoning step to avoid
                          // a duplicate reasoning block appearing after the response.
                          const existingReasoningIdx = steps.findIndex((s: any) => s.type === 'reasoning')
                          const hasToolsBetween = existingReasoningIdx >= 0 &&
                            steps.slice(existingReasoningIdx + 1).some((s: any) => s.type === 'tool_executions')

                          if (existingReasoningIdx >= 0 && !hasToolsBetween) {
                            // Merge: update the existing reasoning step with full accumulated content
                            const reasoningDelta = getReasoningDelta(accumulatedReasoning, previousReasoningContent)
                            const updatedSteps = [...steps]
                            const existingReasoningStep = updatedSteps[existingReasoningIdx]
                            updatedSteps[existingReasoningIdx] = {
                              type: 'reasoning' as const,
                              // findIndex above guarantees this is a reasoning step; the type check narrows the union
                              content: (existingReasoningStep.type === 'reasoning' ? existingReasoningStep.content : '') + reasoningDelta,
                              isStreaming: true
                            }
                            return {
                              ...m,
                              content: accumulatedReasoning,
                              reasoning_content: accumulatedReasoning,
                              is_reasoning: true,
                              steps: updatedSteps
                            }
                          }

                          // Tool calls occurred between reasoning blocks — create a new reasoning step
                          const reasoningDelta = getReasoningDelta(accumulatedReasoning, previousReasoningContent)
                          return {
                            ...m,
                            content: accumulatedReasoning,
                            reasoning_content: accumulatedReasoning,
                            is_reasoning: true,
                            steps: [
                              ...steps,
                              { type: 'reasoning' as const, content: reasoningDelta, isStreaming: true }
                            ]
                          }
                        }
                      })
                    }
                  } else {
                    // Create new streaming message with reasoning step and set isLoading to false
                    const streamingMessage: Message = {
                      role: 'assistant',
                      content: accumulatedReasoning,
                      timestamp: streamingMessageTimestamp,
                      model: model.name,
                      model_id: model.model_id,
                      provider: model.provider,
                      provider_icon_slug: model.provider_icon_slug,
                      provider_icon_url: model.provider_icon_url,
                      model_icon_slug: model.model_icon_slug,
                      model_icon_url: model.model_icon_url,
                      is_reasoning: true,
                      reasoning_content: accumulatedReasoning,
                      steps: [{ type: 'reasoning' as const, content: accumulatedReasoning, isStreaming: true }],
                      message_id: messageId  // Store message ID for file metadata tracking
                    }
                    return {
                      ...c,
                      messages: [...c.messages, streamingMessage],
                      isLoading: false  // Stop showing "Thinking..." once reasoning starts
                    }
                  }
                })
              }
            })
          )
        },

        onToolCallRequest: (approvals: any[], toolCalls: any[]) => {
          // Handle tool call approval requests from the model
          

          setChatGroups(prevGroups =>
            prevGroups.map((group: any) => {
              if (group.id !== activeGroupId) return group

              return {
                ...group,
                chats: group.chats.map((c: Chat) => {
                  if (c.id !== chatId) return c

                  // Check if we already have a streaming message
                  const hasStreamingMessage = c.messages.some((m: Message) =>
                    m.role === 'assistant' && m.timestamp === streamingMessageTimestamp
                  )

                  if (hasStreamingMessage) {
                    // Update existing streaming message with tool calls and pending approvals
                    return {
                      ...c,
                      messages: c.messages.map((m: Message) =>
                        m.timestamp === streamingMessageTimestamp
                          ? {
                              ...m,
                              content: accumulatedContent,
                              reasoning_content: accumulatedReasoning || m.reasoning_content,
                              is_reasoning: false,
                              tool_calls: toolCalls,
                              pending_approvals: approvals.length > 0 ? approvals : m.pending_approvals,
                            }
                          : m
                      )
                    }
                  } else {
                    // Create new streaming message with tool calls and pending approvals
                    const streamingMessage: Message = {
                      role: 'assistant',
                      content: accumulatedContent,
                      timestamp: streamingMessageTimestamp,
                      model: model.name,
                      model_id: model.model_id,
                      provider: model.provider,
                      provider_icon_slug: model.provider_icon_slug,
                      provider_icon_url: model.provider_icon_url,
                      model_icon_slug: model.model_icon_slug,
                      model_icon_url: model.model_icon_url,
                      tool_calls: toolCalls,
                      pending_approvals: approvals.length > 0 ? approvals : undefined,
                      message_id: messageId  // Store message ID for file metadata tracking
                    }
                    return {
                      ...c,
                      messages: [...c.messages, streamingMessage],
                      isLoading: false
                    }
                  }
                })
              }
            })
          )
        },

        onWebSources: (sources: any[]) => {
          // Accumulate web search sources
          accumulatedWebSources = sources

          // Update the message with web search sources
          setChatGroups(prevGroups =>
            prevGroups.map((group: any) => {
              if (group.id !== activeGroupId) return group

              return {
                ...group,
                chats: group.chats.map((c: Chat) => {
                  if (c.id !== chatId) return c

                  // Check if we already have a streaming message
                  const hasStreamingMessage = c.messages.some((m: Message) =>
                    m.role === 'assistant' && m.timestamp === streamingMessageTimestamp
                  )

                  if (hasStreamingMessage) {
                    // Update existing streaming message with web sources
                    return {
                      ...c,
                      messages: c.messages.map((m: Message) =>
                        m.timestamp === streamingMessageTimestamp
                          ? {
                              ...m,
                              web_sources: accumulatedWebSources
                            }
                          : m
                      )
                    }
                  } else {
                    // Create new streaming message with web sources
                    const streamingMessage: Message = {
                      role: 'assistant',
                      content: accumulatedContent,
                      timestamp: streamingMessageTimestamp,
                      model: model.name,
                      model_id: model.model_id,
                      provider: model.provider,
                      provider_icon_slug: model.provider_icon_slug,
                      provider_icon_url: model.provider_icon_url,
                      model_icon_slug: model.model_icon_slug,
                      model_icon_url: model.model_icon_url,
                      web_sources: accumulatedWebSources,
                      message_id: messageId  // Store message ID for file metadata tracking
                    }
                    return {
                      ...c,
                      messages: [...c.messages, streamingMessage],
                      isLoading: false
                    }
                  }
                })
              }
            })
          )
        },

        onImage: (imageData: string) => {
          // Accumulate generated images
          if (imageData && !accumulatedImages.includes(imageData)) {
            accumulatedImages.push(imageData)
            

            // Update the message with accumulated images
            setChatGroups(prevGroups =>
              prevGroups.map((group: any) => {
                if (group.id !== activeGroupId) return group

                return {
                  ...group,
                  chats: group.chats.map((c: Chat) => {
                    if (c.id !== chatId) return c

                    // Check if we already have a streaming message
                    const hasStreamingMessage = c.messages.some((m: Message) =>
                      m.role === 'assistant' && m.timestamp === streamingMessageTimestamp
                    )

                    if (hasStreamingMessage) {
                      // Update existing streaming message with images
                      return {
                        ...c,
                        messages: c.messages.map((m: Message) =>
                          m.timestamp === streamingMessageTimestamp
                            ? {
                                ...m,
                                images: [...accumulatedImages]
                              }
                            : m
                        )
                      }
                    } else {
                      // Create new streaming message with images
                      const streamingMessage: Message = {
                        role: 'assistant',
                        content: accumulatedContent,
                        timestamp: streamingMessageTimestamp,
                        model: model.name,
                        model_id: model.model_id,
                        provider: model.provider,
                        provider_icon_slug: model.provider_icon_slug,
                        provider_icon_url: model.provider_icon_url,
                        model_icon_slug: model.model_icon_slug,
                        model_icon_url: model.model_icon_url,
                        images: [...accumulatedImages],
                        message_id: messageId
                      }
                      return {
                        ...c,
                        messages: [...c.messages, streamingMessage],
                        isLoading: false
                      }
                    }
                  })
                }
              })
            )
          }
        },

        onFileToolExecuting: (toolCalls: any[]) => {
          // Handle file tool execution START - show loading state
          // Also handles UPDATE when placeholder is replaced with real tool call data
          const startTime = Date.now()

          // Check if this is an update to a placeholder (id: "loading" -> real id)
          const isPlaceholderUpdate = toolCalls.length > 0 &&
            toolCalls[0].id !== 'loading' &&
            accumulatedSteps.some((s: any) =>
              s.type === 'tool_executions' &&
              s.isExecuting === true &&
              s.executions?.some((e: any) => e.tool_call?.id === 'loading')
            )

          // Mark the boundary for the next text step - any text after this tool execution
          // should start a new text step from this point in accumulatedContent
          if (!isPlaceholderUpdate) {
            currentTextStepStartIndex = accumulatedContent.length
          }

          // Build file_tool_executions array with loading state for UI display
          // For placeholder updates, preserve the original startTime
          const executions = toolCalls.map((tc) => ({
            tool_call: tc,
            result: null,
            success: null,
            isExecuting: true,  // Mark as currently executing
            startTime  // Track when execution started
          }))

          // Track in accumulatedSteps for persistence
          if (isPlaceholderUpdate) {
            // Find and update the placeholder step instead of adding new one
            const placeholderIndex = accumulatedSteps.findIndex((s: any) =>
              s.type === 'tool_executions' &&
              s.isExecuting === true &&
              s.executions?.some((e: any) => e.tool_call?.id === 'loading')
            )
            if (placeholderIndex !== -1) {
              // Preserve original startTime from placeholder
              const originalStartTime = accumulatedSteps[placeholderIndex].executions?.[0]?.startTime || startTime
              executions.forEach(e => e.startTime = originalStartTime)
              accumulatedSteps[placeholderIndex] = { type: 'tool_executions', executions: [...executions], isExecuting: true }
            }
          } else {
            accumulatedSteps.push({ type: 'tool_executions', executions: [...executions], isExecuting: true })
          }

          

          // Update the message with file tool executions as a new step (loading state)
          setChatGroups(prevGroups =>
            prevGroups.map((group: any) => {
              if (group.id !== activeGroupId) return group

              return {
                ...group,
                chats: group.chats.map((c: Chat) => {
                  if (c.id !== chatId) return c

                  // Check if we already have a streaming message
                  const hasStreamingMessage = c.messages.some((m: Message) =>
                    m.role === 'assistant' && m.timestamp === streamingMessageTimestamp
                  )

                  if (hasStreamingMessage) {
                    // Add tool executions as a new step (loading state)
                    // Or update placeholder step with real tool call data
                    // Also finalize any ongoing reasoning step
                    return {
                      ...c,
                      messages: c.messages.map((m: Message) => {
                        if (m.timestamp !== streamingMessageTimestamp) return m

                        const steps = m.steps || []
                        const lastStep = steps[steps.length - 1]

                        // Check if we're updating a placeholder step (id: "loading" -> real id)
                        const placeholderStepIndex = steps.findIndex((s: any) =>
                          s.type === 'tool_executions' &&
                          s.isExecuting === true &&
                          s.executions?.some((e: any) => e.tool_call?.id === 'loading')
                        )

                        if (placeholderStepIndex !== -1 && toolCalls[0]?.id !== 'loading') {
                          // Update the placeholder step with real tool call data
                          // Preserve the original startTime
                          const placeholderStep = steps[placeholderStepIndex]
                          const originalStartTime = (placeholderStep.type === 'tool_executions' ? placeholderStep.executions?.[0]?.startTime : undefined) || startTime
                          const updatedExecutions = executions.map(e => ({ ...e, startTime: originalStartTime }))
                          return {
                            ...m,
                            steps: [
                              ...steps.slice(0, placeholderStepIndex),
                              { type: 'tool_executions' as const, executions: updatedExecutions, isExecuting: true },
                              ...steps.slice(placeholderStepIndex + 1)
                            ]
                          }
                        }

                        // If last step was reasoning, finalize it before adding tool executions
                        if (lastStep?.type === 'reasoning') {
                          previousReasoningContent = accumulatedReasoning
                          return {
                            ...m,
                            is_reasoning: false,
                            steps: [
                              ...steps.slice(0, -1),
                              { type: 'reasoning' as const, content: lastStep.content, isStreaming: false },
                              { type: 'tool_executions' as const, executions, isExecuting: true }
                            ]
                          }
                        }

                        return {
                          ...m,
                          steps: [
                            ...steps,
                            { type: 'tool_executions' as const, executions, isExecuting: true }
                          ]
                        }
                      })
                    }
                  } else {
                    // Create new streaming message with file tool executions (loading state)
                    const streamingMessage: Message = {
                      role: 'assistant',
                      content: accumulatedContent,
                      timestamp: streamingMessageTimestamp,
                      model: model.name,
                      model_id: model.model_id,
                      provider: model.provider,
                      provider_icon_slug: model.provider_icon_slug,
                      provider_icon_url: model.provider_icon_url,
                      model_icon_slug: model.model_icon_slug,
                      model_icon_url: model.model_icon_url,
                      steps: [{ type: 'tool_executions' as const, executions, isExecuting: true }],
                      message_id: messageId  // Store message ID for file metadata tracking
                    }
                    return {
                      ...c,
                      messages: [...c.messages, streamingMessage],
                      isLoading: false
                    }
                  }
                })
              }
            })
          )
        },

        onFileToolExecuted: (toolCalls: any[], results: any[]) => {
          // Handle file tool execution COMPLETED - update with results

          // Get tool call IDs for matching against executing steps
          const executedToolCallIds = new Set(toolCalls.map(tc => tc.id))

          // Log tool execution results for debugging
          toolCalls.forEach((tc, idx) => {
            const result = results[idx]
            const toolName = tc.function?.name

          })

          // Extract sparks from create_spark tool results
          toolCalls.forEach((tc, idx) => {
            const toolName = tc.function?.name
            if (toolName === 'create_spark' || toolName === 'update_spark') {
              const resultEntry = results[idx]
              // Backend sends: {tool_call, result: {status, spark}, success}
              const toolResult = resultEntry?.result
              if (toolResult?.status === 'success' && toolResult?.spark) {
                // Add spark from tool result (already persisted by backend)
                accumulatedSparksFromTools.push({
                  id: toolResult.spark.id,
                  title: toolResult.spark.title,
                  framework: toolResult.spark.framework,
                  code: toolResult.spark.code, // Code included in tool response
                  version: toolResult.spark.version,
                  assets: toolResult.spark.assets, // Assets available via window.__SPARK_ASSETS__
                  download_url: toolResult.spark.download_url, // For pdf/docx/csv/ics types
                })
              }
            }
          })

          // Build file_tool_executions array for UI display
          // For coding_agent, use the coding_agent_data from the result which contains steps
          const executions = toolCalls.map((tc, idx) => {
            const result = results[idx]
            const baseExec = {
              tool_call: tc,
              result: result,
              success: result?.success !== false,  // Consider success if not explicitly false
              isExecuting: false  // Explicitly mark as completed
            }

            // For coding_agent, include the steps and result from coding_agent_data
            if (CODING_AGENT_TOOLS.has(tc.function?.name)) {
              // Backend sends coding_agent_data with full execution details
              const codingData = result?.coding_agent_data
              const steps = codingData?.steps || accumulatedCodingAgentSteps || []
              return {
                ...baseExec,
                coding_agent_steps: [...steps],
                coding_agent_result: codingData || accumulatedCodingAgentResult || {
                  success: result?.success,
                  summary: result?.summary,
                  files_created: result?.files_created || [],
                  files_modified: result?.files_modified || [],
                },
              }
            }
            return baseExec
          })

          // Auto-open side panel when plan/implement tools succeed
          toolCalls.forEach((tc, idx) => {
            const result = results[idx]
            if (tc.function?.name === 'plan_implementation' && result?.success && result?.data?.plan_id) {
              codeSessionApi.getPlan(result.data.plan_id).then((res) => {
                const store = useProjectPanelStore.getState()
                store.addPlan(res.data)
                store.selectPlan(result.data.plan_id)
                store.openPanel('plans')
              }).catch(console.error)
            }
            if (tc.function?.name === 'implement_plan' && result?.success && result?.data?.plan_id) {
              // Fetch the updated plan (with implementation_branch, status, etc.)
              const store = useProjectPanelStore.getState()
              codeSessionApi.getPlan(result.data.plan_id).then((res) => {
                store.updatePlan(result.data.plan_id, res.data)
                store.selectPlan(result.data.plan_id)
                store.openPanel('plans')
              }).catch(console.error)
            }
          })

          // Track all tool executions for persistence
          allToolExecutions = [...allToolExecutions, ...executions]

          // Update the matching tool_executions step in accumulatedSteps with results
          // Match by tool_call.id to avoid race conditions with multiple concurrent tool calls
          let matchingStepIndex = accumulatedSteps.findLastIndex(
            (s: any) => s.type === 'tool_executions' && s.isExecuting === true &&
              s.executions?.some((e: any) => executedToolCallIds.has(e.tool_call?.id))
          )

          // Fallback: if no match by real ID, try to find placeholder step (id: "loading")
          // This handles race condition where update event hasn't been processed yet
          if (matchingStepIndex === -1) {
            matchingStepIndex = accumulatedSteps.findLastIndex(
              (s: any) => s.type === 'tool_executions' && s.isExecuting === true &&
                s.executions?.some((e: any) => e.tool_call?.id === 'loading')
            )
          }

          if (matchingStepIndex !== -1) {
            accumulatedSteps[matchingStepIndex] = {
              type: 'tool_executions',
              executions: [...executions],
              isExecuting: false
            }
          }

          // Minimum spinner display time
          const minDisplayTime = 1000  // Minimum 1 second visibility

          // Calculate timing ONCE here, not inside the state updater
          const currentTime = Date.now()

          // Get the start time from current state - match by tool_call.id
          const currentGroup = chats.find(c => c.id === chatId)
          const currentMessage = currentGroup?.messages.find(
            (m: Message) => m.role === 'assistant' && m.timestamp === streamingMessageTimestamp
          )
          const currentSteps = currentMessage?.steps || []
          let matchingToolExecIndex = currentSteps.findLastIndex(
            (s: any) => s.type === 'tool_executions' && s.isExecuting === true &&
              s.executions?.some((e: any) => executedToolCallIds.has(e.tool_call?.id))
          )

          // Fallback: if no match by real ID, try to find placeholder step (id: "loading")
          if (matchingToolExecIndex === -1) {
            matchingToolExecIndex = currentSteps.findLastIndex(
              (s: any) => s.type === 'tool_executions' && s.isExecuting === true &&
                s.executions?.some((e: any) => e.tool_call?.id === 'loading')
            )
          }

          let startTime = currentTime
          if (matchingToolExecIndex !== -1) {
            const loadingStep = currentSteps[matchingToolExecIndex]
            // findLastIndex above only matches tool_executions steps; the type check narrows the union
            if (loadingStep.type === 'tool_executions' && loadingStep.executions?.[0]?.startTime) {
              startTime = loadingStep.executions[0].startTime
            }
          }

          const elapsedTime = currentTime - startTime
          const remainingTime = Math.max(0, minDisplayTime - elapsedTime)



          // Capture content that accumulated before tool execution
          // Then immediately reset so new chunks start fresh
          const contentBeforeToolExec = accumulatedContent
          accumulatedContent = ''
          // Also reset the text step start index since accumulatedContent is reset
          currentTextStepStartIndex = 0
          

          // Helper function to update the chat groups (no timing logic inside)
          const updateWithResults = () => {
            setChatGroups(prevGroups =>
              prevGroups.map((group: any) => {
                if (group.id !== activeGroupId) return group

                return {
                  ...group,
                  chats: group.chats.map((c: Chat) => {
                    if (c.id !== chatId) return c

                    // Check if we already have a streaming message
                    const hasStreamingMessage = c.messages.some((m: Message) =>
                      m.role === 'assistant' && m.timestamp === streamingMessageTimestamp
                    )

                    if (hasStreamingMessage) {
                      // Replace the loading step with completed results
                      return {
                        ...c,
                        messages: c.messages.map((m: Message) => {
                          if (m.timestamp !== streamingMessageTimestamp) return m

                          const steps = m.steps || []
                          // Find and replace the tool_executions step that matches by tool_call.id
                          // This prevents race conditions when multiple tools execute concurrently
                          let matchingStepIndex = steps.findLastIndex(
                            (s: any) => s.type === 'tool_executions' && s.isExecuting === true &&
                              s.executions?.some((e: any) => executedToolCallIds.has(e.tool_call?.id))
                          )

                          // Fallback: if no match by real ID, try to find placeholder step (id: "loading")
                          if (matchingStepIndex === -1) {
                            matchingStepIndex = steps.findLastIndex(
                              (s: any) => s.type === 'tool_executions' && s.isExecuting === true &&
                                s.executions?.some((e: any) => e.tool_call?.id === 'loading')
                            )
                          }

                          // Update the steps
                          let updatedSteps = steps
                          if (matchingStepIndex !== -1) {
                            // Replace loading step with completed step
                            updatedSteps = [
                              ...steps.slice(0, matchingStepIndex),
                              { type: 'tool_executions' as const, executions, isExecuting: false },
                              ...steps.slice(matchingStepIndex + 1)
                            ]
                          } else {
                            // No loading step found (rare case - state update race)
                            // Only add if we don't already have results for these tool calls
                            const existingToolIds = new Set(
                              steps.flatMap((s: any) =>
                                s.type === 'tool_executions' && !s.isExecuting
                                  ? s.executions?.map((e: any) => e.tool_call?.id) || []
                                  : []
                              )
                            )
                            const hasNewTools = toolCalls.some(tc => !existingToolIds.has(tc.id))
                            if (hasNewTools) {
                              updatedSteps = [...steps, { type: 'tool_executions' as const, executions, isExecuting: false }]
                            }
                          }

                          // Update file_tool_executions without duplicates
                          const existingExecIds = new Set(
                            (m.file_tool_executions || []).map((e: any) => e.tool_call?.id)
                          )
                          const newExecutions = executions.filter((e: any) => !existingExecIds.has(e.tool_call?.id))

                          return {
                            ...m,
                            file_tool_executions: [...(m.file_tool_executions || []), ...newExecutions],
                            steps: updatedSteps
                          }
                        })
                      }
                    } else {
                      // Create new streaming message with file tool executions
                      const streamingMessage: Message = {
                        role: 'assistant',
                        content: contentBeforeToolExec,
                        timestamp: streamingMessageTimestamp,
                        model: model.name,
                        model_id: model.model_id,
                        provider: model.provider,
                        provider_icon_slug: model.provider_icon_slug,
                        provider_icon_url: model.provider_icon_url,
                        model_icon_slug: model.model_icon_slug,
                        model_icon_url: model.model_icon_url,
                        file_tool_executions: executions,
                        steps: [{ type: 'tool_executions' as const, executions }],
                        message_id: messageId  // Store message ID for file metadata tracking
                      }
                      return {
                        ...c,
                        messages: [...c.messages, streamingMessage],
                        isLoading: false
                      }
                    }
                  })
                }
              })
            )
          }

          // If not enough time has passed, delay the update
          if (remainingTime > 0) {

            setTimeout(() => {
              updateWithResults()
              // No need to set flag - content already reset immediately after capture
            }, remainingTime)
          } else {
            // Enough time has passed, update immediately
            updateWithResults()
            // No need to set flag - content already reset immediately after capture
          }
        },

        onCodingAgentStep: (step: CodingAgentStep) => {
          // Handle Coding Agent agent step progress
          accumulatedCodingAgentSteps.push(step)

          // Also update accumulatedSteps for persistence - find the coding_agent execution and update it
          for (const accStep of accumulatedSteps) {
            if (accStep.type === 'tool_executions') {
              for (const exec of accStep.executions || []) {
                if (CODING_AGENT_TOOLS.has(exec.tool_call?.function?.name)) {
                  exec.coding_agent_steps = [...accumulatedCodingAgentSteps]
                }
              }
            }
          }

          // Update the message with Coding Agent steps (on the last tool_executions step for coding_agent)
          setChatGroups(prevGroups =>
            prevGroups.map((group: any) => {
              if (group.id !== activeGroupId) return group

              return {
                ...group,
                chats: group.chats.map((c: Chat) => {
                  if (c.id !== chatId) return c

                  // Check if we already have a streaming message
                  const hasStreamingMessage = c.messages.some((m: Message) =>
                    m.role === 'assistant' && m.timestamp === streamingMessageTimestamp
                  )

                  if (hasStreamingMessage) {
                    return {
                      ...c,
                      messages: c.messages.map((m: Message) => {
                        if (m.timestamp !== streamingMessageTimestamp) return m

                        // Update coding_agent tool execution in steps with the new step
                        const steps = m.steps || []
                        const updatedSteps = steps.map((s: any) => {
                          if (s.type === 'tool_executions') {
                            return {
                              ...s,
                              executions: s.executions?.map((exec: any) => {
                                if (CODING_AGENT_TOOLS.has(exec.tool_call?.function?.name)) {
                                  return {
                                    ...exec,
                                    coding_agent_steps: [...accumulatedCodingAgentSteps]
                                  }
                                }
                                return exec
                              })
                            }
                          }
                          return s
                        })

                        return {
                          ...m,
                          steps: updatedSteps
                        }
                      })
                    }
                  }
                  return c
                })
              }
            })
          )
        },

        onCodingAgentCompleted: (result: CodingAgentResult) => {
          // Handle Coding Agent agent completion
          accumulatedCodingAgentResult = result

          // Also update accumulatedSteps for persistence - store the final result
          for (const accStep of accumulatedSteps) {
            if (accStep.type === 'tool_executions') {
              for (const exec of accStep.executions || []) {
                if (CODING_AGENT_TOOLS.has(exec.tool_call?.function?.name)) {
                  // Use result.steps if available and has more content than accumulated steps
                  const finalSteps = (result.steps && result.steps.length > accumulatedCodingAgentSteps.length)
                    ? result.steps
                    : accumulatedCodingAgentSteps
                  exec.coding_agent_steps = [...finalSteps]
                  exec.coding_agent_result = result
                  exec.success = result.success
                  exec.isExecuting = false
                }
              }
            }
          }

          // Update the message with Coding Agent result
          setChatGroups(prevGroups =>
            prevGroups.map((group: any) => {
              if (group.id !== activeGroupId) return group

              return {
                ...group,
                chats: group.chats.map((c: Chat) => {
                  if (c.id !== chatId) return c

                  // Check if we already have a streaming message
                  const hasStreamingMessage = c.messages.some((m: Message) =>
                    m.role === 'assistant' && m.timestamp === streamingMessageTimestamp
                  )

                  if (hasStreamingMessage) {
                    return {
                      ...c,
                      messages: c.messages.map((m: Message) => {
                        if (m.timestamp !== streamingMessageTimestamp) return m

                        // Update coding_agent tool execution in steps with the result
                        const steps = m.steps || []
                        const updatedSteps = steps.map((s: any) => {
                          if (s.type === 'tool_executions') {
                            return {
                              ...s,
                              executions: s.executions?.map((exec: any) => {
                                if (CODING_AGENT_TOOLS.has(exec.tool_call?.function?.name)) {
                                  // Use result.steps if available and has more content than accumulated steps
                                  // This ensures we show the complete steps from the final result
                                  const finalSteps = (result.steps && result.steps.length > accumulatedCodingAgentSteps.length)
                                    ? result.steps
                                    : accumulatedCodingAgentSteps
                                  return {
                                    ...exec,
                                    coding_agent_steps: [...finalSteps],
                                    coding_agent_result: result,
                                    success: result.success,
                                    isExecuting: false
                                  }
                                }
                                return exec
                              }),
                              isExecuting: false
                            }
                          }
                          return s
                        })

                        return {
                          ...m,
                          steps: updatedSteps
                        }
                      })
                    }
                  }
                  return c
                })
              }
            })
          )
        },

        onCodingAgentQuestion: (data: CodingAgentQuestion) => {
          // Store pending question and trigger re-render
          pendingCodingAgentQuestionRef.current = data
          setPendingQuestionVersion(v => v + 1)
        },

        onPreviewStarted: (data: { port: number; command: string; pid: number }) => {
          window.dispatchEvent(new CustomEvent('preview:started', { detail: data }))
        },

        onContextCompacted: (data: ContextCompactedData) => {
          // Handle context compaction notification - show subtle toast
          const tokensSavedK = Math.round(data.tokens_saved / 1000)
          toast({
            title: 'Context optimized',
            description: `Summarized ${data.original_messages - data.compacted_messages} messages to continue seamlessly (saved ~${tokensSavedK}k tokens)`,
            duration: 4000,
          })
        },

        onSternaRoute: (data) => {
          sternaRouteData = data
        },

        onGenerationId: (id) => {
          generationId = id
        },

        onUsageUpdate: (data) => {
          lastUsageUpdate = data
          if (data.generation_id) generationId = data.generation_id
          if (data.generation_ids) generationIds = data.generation_ids
        },

        onDone: (metadata: any) => {
          // Capture metadata for final update (only used for final done event)
          messageMetadata = metadata
          if (metadata.generation_id) generationId = metadata.generation_id
          if (metadata.generation_ids) generationIds = metadata.generation_ids
        },

        onError: (error: string, detail?: string, code?: string) => {
          console.error('[sendToModel] Stream error:', error, detail, code)

          // Actionable errors (no_api_key, invalid_api_key, insufficient_credits)
          // arrive with a backend-authored message + machine code — keep the
          // message verbatim so it matches the resolution actions we render.
          const rawError = error || detail || ''
          const errorMessage = code
            ? (error || 'An error occurred while processing the response.')
            : (getUserFriendlyErrorMessage(rawError) || 'An error occurred while processing the response. Please try again.')

          // Update chat to show error state
          setChatGroups(prevGroups =>
            prevGroups.map((group: any) => {
              if (group.id !== activeGroupId) return group

              return {
                ...group,
                chats: group.chats.map((c: Chat) => {
                  if (c.id !== chatId) return c

                  // Check if streaming message exists
                  const hasStreamingMessage = c.messages.some((m: Message) =>
                    m.role === 'assistant' && m.timestamp === streamingMessageTimestamp
                  )

                  if (hasStreamingMessage) {
                    // Update existing streaming message with error
                    return {
                      ...c,
                      messages: c.messages.map((m: Message) => {
                        if (m.timestamp !== streamingMessageTimestamp) return m

                        // Mark message as failed with error
                        return {
                          ...m,
                          error: errorMessage,
                          errorCode: code,
                          isError: true,  // Important: marks stream as complete
                          is_interrupted: true
                        }
                      }),
                      isLoading: false
                    }
                  } else {
                    // Create new error message (error occurred before any content
                    // was streamed). Content carries the friendly message so the
                    // message is visible — MessageList filters out isError
                    // messages with empty content.
                    const errorAssistantMessage: Message = {
                      role: 'assistant',
                      content: errorMessage,
                      timestamp: streamingMessageTimestamp,
                      model: model.name,
                      model_id: model.model_id,
                      provider: model.provider,
                      provider_icon_slug: model.provider_icon_slug,
                      provider_icon_url: model.provider_icon_url,
                      model_icon_slug: model.model_icon_slug,
                      model_icon_url: model.model_icon_url,
                      error: errorMessage,
                      errorCode: code,
                      isError: true,  // Important: marks stream as complete
                      is_interrupted: true
                    }
                    return {
                      ...c,
                      messages: [...c.messages, errorAssistantMessage],
                      isLoading: false
                    }
                  }
                })
              }
            })
          )
        },
      },
      { controller, uploadedFiles: uploadedFiles.length > 0 ? uploadedFiles : undefined })

      // Stream completed successfully
      const endTime = Date.now()
      const durationSeconds = (endTime - startTime) / 1000

      // Detect if this was an abort (user clicked Stop)
      const wasAborted = controller.signal.aborted

      // If a coding agent question is pending and user cancelled, send cancel answer
      if (wasAborted && pendingCodingAgentQuestionRef.current) {
        codeSessionApi.sendCodingAgentAnswer(chatId, '__CANCELLED__').catch(() => {})
        pendingCodingAgentQuestionRef.current = null
        setPendingQuestionVersion(v => v + 1)
      }

      // Clear pending question on completion
      if (pendingCodingAgentQuestionRef.current) {
        pendingCodingAgentQuestionRef.current = null
        setPendingQuestionVersion(v => v + 1)
      }

      // Build effective metadata: use onDone data, or fallback to usage_update, or estimate
      let effectiveUsage = messageMetadata?.usage ?? null
      let effectiveCost = messageMetadata?.cost ?? undefined
      let effectivePromptCost = messageMetadata?.prompt_cost ?? undefined
      let effectiveCompletionCost = messageMetadata?.completion_cost ?? undefined

      // For aborted messages: use lastUsageUpdate immediately (if available).
      // The precise OpenRouter query happens AFTER persistence (background).
      if (!effectiveUsage && wasAborted && lastUsageUpdate) {
        effectiveUsage = lastUsageUpdate.usage
        effectiveCost = lastUsageUpdate.cost
        effectivePromptCost = lastUsageUpdate.prompt_cost
        effectiveCompletionCost = lastUsageUpdate.completion_cost
      }

      // Final update with duration and stop loading

      // Get sparks from tool results first (already persisted by backend)
      // Fall back to parsing from content (legacy method) or metadata
      // Extract outside setChatGroups callback so it's available for persistence
      const sparksFromTools = accumulatedSparksFromTools
      const parsedSparks = extractSparks(accumulatedContent)
      // Priority: 1) Sparks from create_spark tool, 2) Parsed from content, 3) From metadata
      const sparksToUse = sparksFromTools.length > 0
        ? sparksFromTools
        : (parsedSparks.length > 0 ? parsedSparks : (messageMetadata?.sparks || []))
      const sparksAlreadyPersisted = sparksFromTools.length > 0 // Don't re-persist tool-created sparks

      // Auto-open the sparks side panel if sparks were created/updated via tools
      if (sparksFromTools.length > 0) {
        // Open the side panel with the most recently created/updated spark
        const latestSpark = sparksFromTools[sparksFromTools.length - 1]
        useArtifactsPanelStore.getState().openSparkInPanel(latestSpark.id)
      }

      setChatGroups(prevGroups =>
        prevGroups.map((group: any) => {
          if (group.id !== activeGroupId) return group

          return {
            ...group,
            chats: group.chats.map((c: Chat) => {
              if (c.id !== chatId) return c

              return {
                ...c,
                messages: c.messages.map((m: Message) => {
                  if (m.timestamp === streamingMessageTimestamp) {
                    // Clear any stuck isExecuting states and remove duplicate steps (safety cleanup)
                    // Collect all completed tool_call IDs to identify duplicates
                    const completedToolCallIds = new Set<string>()
                    for (const step of (m.steps || [])) {
                      if (step.type === 'tool_executions' && !step.isExecuting) {
                        for (const exec of (step.executions || [])) {
                          if (exec.tool_call?.id) {
                            completedToolCallIds.add(exec.tool_call.id)
                          }
                        }
                      }
                    }

                    // Filter out orphaned executing steps (ones that have completed duplicates)
                    // and mark remaining executing steps as complete
                    const cleanedSteps = (m.steps || [])
                      .filter((step: any) => {
                        if (step.type === 'tool_executions' && step.isExecuting) {
                          // Check if all tool calls in this step have completed duplicates
                          const allHaveCompletedDuplicates = (step.executions || []).every(
                            (exec: any) => exec.tool_call?.id && completedToolCallIds.has(exec.tool_call.id)
                          )
                          // Remove this step if all its tool calls already have completed versions
                          if (allHaveCompletedDuplicates && step.executions?.length > 0) {
                            return false
                          }
                        }
                        return true
                      })
                      .map((step: any) => {
                        if (step.type === 'tool_executions' && step.isExecuting) {
                          return {
                            ...step,
                            isExecuting: false,
                            executions: step.executions?.map((exec: any) => ({
                              ...exec,
                              isExecuting: false
                            }))
                          }
                        }
                        return step
                      })

                    const updatedMessage = {
                      ...m,
                      content: accumulatedContent,
                      reasoning_content: accumulatedReasoning || m.reasoning_content,
                      web_sources: accumulatedWebSources.length > 0 ? accumulatedWebSources : m.web_sources,
                      is_reasoning: false,
                      steps: cleanedSteps,
                      // Add usage data - from onDone metadata, or effective usage (abort fallback)
                      ...(effectiveUsage && {
                        tokens: {
                          prompt: effectiveUsage.prompt_tokens,
                          completion: effectiveUsage.completion_tokens,
                          total: effectiveUsage.total_tokens,
                        }
                      }),
                      ...(effectiveCost !== undefined && { cost: effectiveCost }),
                      ...(effectivePromptCost !== undefined && { prompt_cost: effectivePromptCost }),
                      ...(effectiveCompletionCost !== undefined && { completion_cost: effectiveCompletionCost }),
                      // Add finish_reason to indicate streaming is complete (used by voice conversation auto-read)
                      ...(messageMetadata?.finish_reason && { finish_reason: wasAborted ? 'cancelled' : messageMetadata.finish_reason }),
                      ...(wasAborted && { is_stopped: true }),
                      // Add sparks (interactive React components)
                      ...(sparksToUse.length > 0 && { sparks: sparksToUse }),
                      // Add Sterna routing info (auto-router resolved model)
                      ...(sternaRouteData && { sterna_route: sternaRouteData }),
                      latency: durationSeconds,
                    }
                    
                    return updatedMessage
                  }
                  return m
                }),
                isLoading: false
              }
            }),
            updatedAt: new Date()
          }
        })
      )

      // Clean up controller
      abortControllersRef.current.delete(chatId)

      // Refresh quota status in background (non-blocking)
      // This updates the UI to show updated usage after the message
      refreshQuotaAfterUsage()

      // Persist assistant message to the database (async, non-blocking)
      // Use totalContentForPersistence which never gets reset (unlike accumulatedContent which resets after tool executions)
      const contentToPersist = totalContentForPersistence || accumulatedContent
      

      // Persist if there's text content OR tool executions (image generation may have minimal text)
      if (contentToPersist.trim() || allToolExecutions.length > 0) {
        // Django DecimalField has max_digits=10, decimal_places=6
        // Round to 6 decimal places to avoid floating-point precision issues
        const costValue = effectiveCost !== undefined
          ? parseFloat(String(effectiveCost)).toFixed(6)
          : undefined

        // Build the message payload - only include defined fields
        const messagePayload: any = {
          role: 'assistant',
          content: contentToPersist,
          model_id: model.model_id,
          model_provider: model.provider,
          ...(wasAborted && { is_stopped: true }),
        }

        // Only include optional fields if they have values
        if (effectiveUsage?.prompt_tokens !== undefined) {
          messagePayload.prompt_tokens = effectiveUsage.prompt_tokens
        }
        if (effectiveUsage?.completion_tokens !== undefined) {
          messagePayload.completion_tokens = effectiveUsage.completion_tokens
        }
        if (costValue !== undefined) {
          messagePayload.cost = costValue
        }
        // Use the tracked interleaved steps for persistence
        // accumulatedSteps preserves the correct order: text -> tool_executions -> text -> ...
        // This ensures the same display structure after reload as during streaming
        const persistedSteps: any[] = []

        // Add reasoning step at the beginning if present
        if (accumulatedReasoning) {
          persistedSteps.push({ type: 'reasoning', content: accumulatedReasoning, isStreaming: false })
        }

        // Add all tracked steps (text and tool_executions in their interleaved order)
        for (const step of accumulatedSteps) {
          if (step.type === 'text' && step.content?.trim()) {
            persistedSteps.push({ type: 'text', content: step.content })
          } else if (step.type === 'tool_executions') {
            // Clean up isExecuting flag for persistence (both step-level and execution-level)
            // Explicitly include coding_agent_steps and coding_agent_result for persistence
            persistedSteps.push({
              type: 'tool_executions',
              executions: step.executions?.map((exec: any) => ({
                ...exec,
                isExecuting: false,
                // Ensure coding agent data persists
                ...(exec.coding_agent_steps && { coding_agent_steps: exec.coding_agent_steps }),
                ...(exec.coding_agent_result && { coding_agent_result: exec.coding_agent_result }),
              })),
              isExecuting: false
            })
          }
        }

        // Only include steps if there are any
        if (persistedSteps.length > 0) {
          messagePayload.steps = persistedSteps
        }

        // Include web sources in metadata for persistence
        if (accumulatedWebSources.length > 0) {
          messagePayload.metadata = {
            ...(messagePayload.metadata || {}),
            web_sources: accumulatedWebSources
          }
        }

        conversationsAPI.createMessage(activeGroupId, chatId, messagePayload).then((createdMessage) => {
          if (wasAborted && generationId && createdMessage?.id) {
            // Query ALL generation IDs for comprehensive abort billing
            // Each iteration of the LLM tool loop has its own generation ID
            const idsToQuery = generationIds.length > 0 ? generationIds : [generationId]
            Promise.all(idsToQuery.map(id => llmApi.getGenerationUsage(id).catch(() => null))).then((results) => {
              // Sum up usage from all generation IDs
              let totalGenPrompt = 0
              let totalGenCompletion = 0
              let totalGenCost = 0
              for (const genData of results) {
                if (!genData) continue
                totalGenPrompt += genData.usage?.prompt_tokens || 0
                totalGenCompletion += genData.usage?.completion_tokens || 0
                totalGenCost += genData.cost || 0
              }

              const billingUpdate: any = {
                prompt_tokens: totalGenPrompt,
                completion_tokens: totalGenCompletion,
                cost: totalGenCost.toFixed(6),
              }
              // Patch DB
              conversationsAPI.updateMessage(activeGroupId, chatId, createdMessage.id, billingUpdate).catch(() => {})
              // Update React state so billing shows in UI immediately
              setChatGroups(prevGroups =>
                prevGroups.map((group: any) => {
                  if (group.id !== activeGroupId) return group
                  return {
                    ...group,
                    chats: group.chats.map((c: Chat) => {
                      if (c.id !== chatId) return c
                      return {
                        ...c,
                        messages: c.messages.map((m: Message) => {
                          if (m.timestamp !== streamingMessageTimestamp) return m
                          return {
                            ...m,
                            message_id: createdMessage.id,
                            tokens: {
                              prompt: billingUpdate.prompt_tokens,
                              completion: billingUpdate.completion_tokens,
                              total: billingUpdate.prompt_tokens + billingUpdate.completion_tokens,
                            },
                            cost: parseFloat(billingUpdate.cost),
                          }
                        }),
                      }
                    }),
                  }
                })
              )
            }).catch(() => {})
          }
        }).catch((error) => {
          console.error(`[sendToModel] ❌ Failed to persist assistant message to chat ${chatId}:`, error)
        })

        // Persist sparks to the database (async, non-blocking)
        // Skip if sparks were created via create_spark tool (already persisted by backend)
        if (sparksToUse.length > 0 && !sparksAlreadyPersisted) {
          sparksAPI.createBatch(sparksToUse, chatId, messageId).catch((error) => {
            console.error(`[sendToModel] ❌ Failed to persist sparks for chat ${chatId}:`, error)
          })
        }
      } else {
        console.warn(`[sendToModel] ⚠️ No content to persist for assistant message in chat ${chatId}`)
      }

    } catch (error: any) {
      // Clean up controller on error
      abortControllersRef.current.delete(chatId)

      console.error(`[sendToModel] Error for ${model.name}:`, error)

      // Check if it was an abort
      if (error.name === 'AbortError' || error.message?.includes('aborted')) {

        // Save partial content to DB immediately (billing data will be patched in background)
        const contentToPersist = totalContentForPersistence || accumulatedContent
        if (contentToPersist.trim() || allToolExecutions.length > 0) {
          // Use lastUsageUpdate for immediate persistence (available from completed iterations)
          const messagePayload: any = {
            role: 'assistant',
            content: contentToPersist,
            model_id: model.model_id,
            model_provider: model.provider,
            is_stopped: true,
            ...(lastUsageUpdate && {
              prompt_tokens: lastUsageUpdate.usage.prompt_tokens,
              completion_tokens: lastUsageUpdate.usage.completion_tokens,
              cost: parseFloat(String(lastUsageUpdate.cost)).toFixed(6),
            }),
          }

          // Build steps (reuse same logic as onDone path)
          const persistedSteps: any[] = []
          if (accumulatedReasoning) {
            persistedSteps.push({ type: 'reasoning', content: accumulatedReasoning, isStreaming: false })
          }
          for (const step of accumulatedSteps) {
            if (step.type === 'text' && step.content?.trim()) {
              persistedSteps.push({ type: 'text', content: step.content })
            } else if (step.type === 'tool_executions') {
              const completedExecs = step.executions?.filter((exec: any) =>
                !exec.isExecuting || exec.result
              ).map((exec: any) => ({
                ...exec,
                isExecuting: false,
                ...(exec.coding_agent_steps && { coding_agent_steps: exec.coding_agent_steps }),
                ...(exec.coding_agent_result && { coding_agent_result: exec.coding_agent_result }),
              }))
              if (completedExecs?.length > 0) {
                persistedSteps.push({
                  type: 'tool_executions',
                  executions: completedExecs,
                  isExecuting: false,
                })
              }
            }
          }
          if (persistedSteps.length > 0) messagePayload.steps = persistedSteps
          if (accumulatedWebSources.length > 0) {
            messagePayload.metadata = { web_sources: accumulatedWebSources }
          }

          try {
            const createdMessage = await conversationsAPI.createMessage(activeGroupId, chatId, messagePayload)
            // Query OpenRouter in background for precise billing, then PATCH
            if (generationId && createdMessage?.id) {
              llmApi.getGenerationUsage(generationId).then((genData) => {
                const billingUpdate: any = {}
                if (lastUsageUpdate) {
                  billingUpdate.prompt_tokens = lastUsageUpdate.usage.prompt_tokens + genData.usage.prompt_tokens
                  billingUpdate.completion_tokens = lastUsageUpdate.usage.completion_tokens + genData.usage.completion_tokens
                  billingUpdate.cost = ((lastUsageUpdate.cost || 0) + (genData.cost || 0)).toFixed(6)
                } else {
                  billingUpdate.prompt_tokens = genData.usage.prompt_tokens
                  billingUpdate.completion_tokens = genData.usage.completion_tokens
                  billingUpdate.cost = genData.cost.toFixed(6)
                }
                // Patch DB
                conversationsAPI.updateMessage(activeGroupId, chatId, createdMessage.id, billingUpdate).catch(
                  e => console.warn('[sendToModel] Failed to patch billing data:', e)
                )
                // Update React state so billing shows in UI immediately
                setChatGroups(prevGroups =>
                  prevGroups.map((group: any) => {
                    if (group.id !== activeGroupId) return group
                    return {
                      ...group,
                      chats: group.chats.map((c: Chat) => {
                        if (c.id !== chatId) return c
                        return {
                          ...c,
                          messages: c.messages.map((m: Message) => {
                            if (m.timestamp !== streamingMessageTimestamp) return m
                            return {
                              ...m,
                              message_id: createdMessage.id,
                              tokens: {
                                prompt: billingUpdate.prompt_tokens,
                                completion: billingUpdate.completion_tokens,
                                total: billingUpdate.prompt_tokens + billingUpdate.completion_tokens,
                              },
                              cost: parseFloat(billingUpdate.cost),
                            }
                          }),
                        }
                      }),
                    }
                  })
                )
              }).catch(() => {})
            }
          } catch {
            // Non-critical: message content is already in React state
          }
        }

        // Set loading to false but don't show error message
        setChatGroups(prevGroups =>
          prevGroups.map((group: any) =>
            group.id === activeGroupId
              ? {
                  ...group,
                  chats: group.chats.map((c: Chat) =>
                    c.id === chatId ? { ...c, isLoading: false } : c
                  ),
                  updatedAt: new Date()
                }
              : group
          )
        )
        return
      }

      // Handle actual errors (not aborts)
      // Convert technical error to user-friendly message
      const errorMessage = getUserFriendlyErrorMessage(error)

      // Add error message to chat
      setChatGroups(prevGroups =>
        prevGroups.map((group: any) => {
          if (group.id !== activeGroupId) return group

          return {
            ...group,
            chats: group.chats.map((c: Chat) => {
              if (c.id !== chatId) return c

              const errorMsg: Message = {
                role: 'assistant',
                content: `Error: ${errorMessage}`,
                timestamp: new Date(),
                model: model.name,
                model_id: model.model_id,
                provider: model.provider,
                provider_icon_slug: model.provider_icon_slug,
                provider_icon_url: model.provider_icon_url,
                model_icon_slug: model.model_icon_slug,
                model_icon_url: model.model_icon_url,
                isError: true,
                message_id: messageId  // Store message ID for file metadata tracking
              }

              return {
                ...c,
                messages: [...c.messages, errorMsg],
                isLoading: false
              }
            }),
            updatedAt: new Date()
          }
        })
      )

      toast({
        title: 'Error',
        description: errorMessage,
        variant: 'destructive'
      })
    }
  }, [chats, activeGroupId, setChatGroups, toast, isAuthenticated, openModal, getAuthModalVariant, streamResponsesSetting, voiceConversationActive, refreshQuotaAfterUsage])

  // Generate a conversation title based on the first user message
  const generateConversationTitle = useCallback(async (userMessage: string, model: Model) => {
    // Get store actions for streaming title updates
    const { startGeneratingTitle, updateGeneratingTitle, finishGeneratingTitle, triggerRefresh } = useActiveConversationStore.getState()

    try {
      const prompt = `Generate a short, concise title (3-6 words max) for a conversation that starts with this message. Return ONLY the title, no quotes, no explanation, no punctuation at the end.

User message: "${userMessage.slice(0, 500)}"`

      let title = ''

      // Start streaming title generation (for real-time sidebar updates)
      // This also adds a temporary newConversation to the store for immediate display
      startGeneratingTitle(activeGroupId, 'New Conversation')

      await llmApi.completeStream({
        model: model.model_id,
        messages: [{ role: 'user', content: prompt }],
        temperature: 0.3,
        max_tokens: 30,
        stream: true,
      }, {
        onContent: (content: string) => {
          title += content
          // Clean as we go for display (remove quotes, etc.)
          const cleanedTitle = title.trim().replace(/^["']|["']$/g, '').replace(/\.$/, '').trim()
          // Update the store for real-time sidebar display
          updateGeneratingTitle(cleanedTitle)
        },
        onDone: () => {},
        onError: (error: string) => {
          console.error('[generateConversationTitle] Error:', error)
        },
      })

      // Clean up the title (remove quotes, trim, etc.)
      title = title.trim().replace(/^["']|["']$/g, '').replace(/\.$/, '').trim()

      if (title && title.length > 0 && title.length < 100) {
        // Update the conversation name in the chat groups
        setChatGroups(prevGroups =>
          prevGroups.map((group: any) => {
            if (group.id !== activeGroupId) return group
            // Only update if not already custom named
            if (group.isCustomName) return group
            return {
              ...group,
              name: title,
              updatedAt: new Date(),
            }
          })
        )
        

        // Finish streaming with the final title (keeps it in store until localStorage updates)
        finishGeneratingTitle(title)
      } else {
        // No valid title, just finish
        finishGeneratingTitle()
      }

      // Trigger refresh to update sidebar (will use newConversation from store until localStorage catches up)
      triggerRefresh()
    } catch (error) {
      console.error('[generateConversationTitle] Failed:', error)
      // Make sure to finish even on error
      finishGeneratingTitle()
      triggerRefresh()
      // Silently fail - title generation is not critical
    }
  }, [activeGroupId, setChatGroups])

  const composeAndSend = useCallback(async (
    targetChatIds: string[],
    content: string,
    localAttachments: Attachment[],
    isToolContinuation: boolean = false  // Flag to bypass empty content check
  ) => {
    

    // Auth check
    if (!isAuthenticated) {
      toast({ title: 'Authentication required', description: 'Please sign in to send messages', variant: 'destructive' })
      const variant = getAuthModalVariant()
      openModal(variant, window.location.pathname)
      return
    }

    // Allow empty messages if continuing after tool execution
    if (!isToolContinuation && !content.trim() && localAttachments.length === 0) {
      
      return
    }

    // Track asset references for persistence (populated after upload)
    let assetRefs: AssetReference[] = []

    // Start asset upload in parallel (will await before persistence)
    // Assets are stored per-chat, so use the first target chat ID
    const primaryChatId = targetChatIds[0]
    const assetUploadPromise = localAttachments.length > 0 && !isToolContinuation && primaryChatId
      ? uploadAttachmentsAsAssets(primaryChatId, localAttachments)
      : Promise.resolve({ enriched: localAttachments, assetRefs: [] })

    const imageAttachments = localAttachments.filter(a => a.type === 'image')
    const fileAttachments = localAttachments.filter(a => a.type === 'file')
    const pdfAttachments = fileAttachments.filter(f => (f as any).base64 && !(f as any).textContent && f.file && isPDFFile(f.file))
    const officeAttachments = fileAttachments.filter(f => (f as any).base64 && !(f as any).textContent && f.file && isOfficeFile(f.file))
    const hasImages = imageAttachments.length > 0
    const hasPDFs = pdfAttachments.length > 0
    const hasOfficeFiles = officeAttachments.length > 0
    const hasText = content.trim().length > 0
    const timestamp = new Date()

    let updatedChats: Chat[] = []

    setChatGroups(prevGroups =>
      prevGroups.map((group: any) => {
        if (group.id !== activeGroupId) return group

        const updatedGroupChats = group.chats.map((chat: Chat) => {
          if (!targetChatIds.includes(chat.id)) return chat
          if ((chat as any).disabled || chat.model === null) return chat

          const supportsVision = chat.model.input_modalities?.includes('image')
          const supportsFiles = chat.model.input_modalities?.includes('file')
          const messages = [...chat.messages]

          // Add user message only if not a tool continuation
          // (tool continuations just send existing messages including the tool result)
          if (!isToolContinuation) {
            const userMessage: Message = {
              role: 'user',
              content: content,
              timestamp,
              attachments: localAttachments.length > 0 ? localAttachments : undefined,
            }
            messages.push(userMessage)
          }

          // Unsupported attachments notice
          const unsupportedMessage = buildUnsupportedAttachmentsMessage(
            hasImages,
            hasPDFs,
            hasOfficeFiles,
            hasText,
            supportsVision,
            supportsFiles
          )

          if (unsupportedMessage) {
            messages.push({
              role: 'assistant',
              content: unsupportedMessage,
              timestamp: new Date(),
              model: chat.model.name,
              model_id: chat.model.model_id,
              provider: chat.model.provider,
              provider_icon_slug: chat.model.provider_icon_slug,
              provider_icon_url: chat.model.provider_icon_url,
              model_icon_slug: chat.model.model_icon_slug,
              model_icon_url: chat.model.model_icon_url,
              isUnsupported: true,
            })
          }

          return { ...chat, messages }
        })

        updatedChats = updatedGroupChats
        return { ...group, chats: updatedGroupChats, updatedAt: new Date() }
      })
    )

    // Persist user messages to the database
    // Wait for asset upload to complete first so we can include asset references
    

    if (!isToolContinuation && (content.trim() || localAttachments.length > 0)) {
      // Wait for asset upload to complete
      const { assetRefs: uploadedAssetRefs } = await assetUploadPromise.catch(err => {
        console.error('[composeAndSend] Asset upload failed, persisting without asset refs:', err)
        return { enriched: localAttachments, assetRefs: [] as AssetReference[] }
      })
      assetRefs = uploadedAssetRefs

      // Build message content with asset references if we have any
      let messageContent: any = content
      if (assetRefs.length > 0) {
        // Store as multipart content: text + asset references
        const parts: any[] = []
        if (content.trim()) {
          parts.push({ type: 'text', text: content })
        }
        // Add asset references
        for (const ref of assetRefs) {
          parts.push(ref)
        }
        messageContent = parts.length === 1 && parts[0].type === 'text' ? content : parts
      }

      const persistPromises = targetChatIds.map(async (chatId) => {
        try {
          await conversationsAPI.createMessage(activeGroupId, chatId, {
            role: 'user',
            content: messageContent,
          })
          
        } catch (error) {
          console.error(`[composeAndSend] ❌ Failed to persist user message to chat ${chatId}:`, error)
        }
      })
      // Don't await - persist in background
      Promise.all(persistPromises).catch(console.error)
    }

    // Check if this is the first message in the conversation (for title generation)
    // Only generate title if:
    // 1. Not a tool continuation
    // 2. No existing user messages in any chat before this one
    // 3. Conversation doesn't have a custom name
    const activeGroup = chatGroups.find((g: any) => g.id === activeGroupId)
    const isFirstMessage = !isToolContinuation &&
      activeGroup &&
      !activeGroup.isCustomName &&
      !activeGroup.chats.some((c: any) => c.messages.some((m: any) => m.role === 'user'))

    // Send to targets in parallel using updated state
    const enabledChats = updatedChats.filter(c => targetChatIds.includes(c.id) && c.model !== null && !(c as any).disabled)

    // Track each model as recently used (for "Recent Chat Models" section in dropdown)
    enabledChats.forEach(c => {
      if (c.model) {
        addRecentChatModel(c.model.model_id, c.model as any)
      }
    })

    const promises = enabledChats.map(c => sendToModel(c.id, c.model!, c.messages))
    await Promise.all(promises)

    // Generate title after first message is sent (async, non-blocking)
    // Also generate title for attachment-only messages using filenames
    if (isFirstMessage && enabledChats.length > 0) {
      const firstModel = enabledChats[0].model
      if (firstModel) {
        // Use text content if available, otherwise describe attachments
        let titleInput = content.trim()
        if (!titleInput && localAttachments.length > 0) {
          const fileNames = localAttachments.map(a => a.file?.name || 'file').join(', ')
          titleInput = `Attached files: ${fileNames}`
        }
        if (titleInput) {
          // Run title generation asynchronously without blocking
          generateConversationTitle(titleInput, firstModel)
        }
      }
    }
  }, [chats, chatGroups, activeGroupId, setChatGroups, toast, isAuthenticated, openModal, getAuthModalVariant, sendToModel, generateConversationTitle, addRecentChatModel])

  // Shared input entry point (synced): just call composeAndSend for all enabled chats
  const sendMessage = useCallback((content: string) => {
    const enabledIds = chats.filter(c => c.model !== null && !(c as any).disabled).map(c => c.id)
    if (enabledIds.length === 0) return

    // Take a snapshot of current attachments with enriched metadata for serialization survival
    const currentAttachments = attachments.map(att => ({
      ...att,
      // Extract File metadata at root level so they survive JSON serialization
      fileName: att.file.name,
      fileType: att.file.type,
      fileSize: att.file.size,
    } as any))

    composeAndSend(enabledIds, content, currentAttachments)

    // Clear attachments after sending
    setAttachments([])
  }, [chats, attachments, setAttachments, composeAndSend])

  // Send a spark fix message with spark_fix_request metadata
  const sendSparkFixMessage = useCallback(async (
    chatId: string,
    content: string,
    sparkFixRequest: { spark_id: string; spark_title: string; error: string }
  ) => {
    const chat = chats.find(c => c.id === chatId)
    if (!chat?.model) return

    // Create a user message for the fix request
    const userMessage: Message = {
      role: 'user',
      content,
      timestamp: new Date(),
    }

    // Get current messages and add the fix request message
    const messages = [...chat.messages, userMessage]

    // Update UI with the user message first
    setChatGroups(prevGroups =>
      prevGroups.map((group: any) =>
        group.id === activeGroupId
          ? {
              ...group,
              chats: group.chats.map((c: Chat) =>
                c.id === chatId
                  ? { ...c, messages }
                  : c
              ),
              updatedAt: new Date(),
            }
          : group
      )
    )

    // Send to model with spark_fix_request metadata and ensure sparks is enabled
    await sendToModel(chatId, chat.model, messages, {
      sparkFixRequest,
      parameterOverrides: { enable_sparks: true }
    })
  }, [chats, activeGroupId, setChatGroups, sendToModel])

  // Send a spark ignite message with spark_ignite_request metadata
  const sendIgniteMessage = useCallback(async (
    chatId: string,
    sparkIgniteRequest: { spark_id: string; spark_title: string }
  ) => {
    const chat = chats.find(c => c.id === chatId)
    if (!chat?.model) return

    const content = `Turn the spark "${sparkIgniteRequest.spark_title}" into a full Next.js project that I can preview and deploy.`
    const userMessage: Message = {
      role: 'user',
      content,
      timestamp: new Date(),
    }

    const messages = [...chat.messages, userMessage]

    // Update UI with the user message first
    setChatGroups(prevGroups =>
      prevGroups.map((group: any) =>
        group.id === activeGroupId
          ? {
              ...group,
              chats: group.chats.map((c: Chat) =>
                c.id === chatId
                  ? { ...c, messages }
                  : c
              ),
              updatedAt: new Date(),
            }
          : group
      )
    )

    // Send to model with spark_ignite_request metadata and ensure sparks + file tools are enabled
    await sendToModel(chatId, chat.model, messages, {
      sparkIgniteRequest,
      parameterOverrides: { enable_sparks: true, enable_file_tools: true }
    })

    // After ignite completes, refresh spark data to pick up is_ignited=true
    try {
      const refreshed = await sparksAPI.get(sparkIgniteRequest.spark_id)
      if (refreshed?.is_ignited) {
        setChatGroups((prev: any[]) =>
          prev.map((group: any) =>
            group.id !== activeGroupId ? group : {
              ...group,
              chats: group.chats.map((c: any) => ({
                ...c,
                messages: c.messages.map((m: any) => ({
                  ...m,
                  sparks: m.sparks?.map((s: any) =>
                    s.id === sparkIgniteRequest.spark_id ? { ...s, is_ignited: true } : s
                  ),
                })),
              })),
            }
          )
        )
      }
    } catch { /* non-critical — page reload will pick up correct state */ }
  }, [chats, activeGroupId, setChatGroups, sendToModel])

  // Answer a pending coding agent question
  const answerCodingAgentQuestion = useCallback((chatId: string, answer: string) => {
    codeSessionApi.sendCodingAgentAnswer(chatId, answer).catch((err) => {
      console.error('[CodingAgent] Failed to send answer:', err)
    })
    pendingCodingAgentQuestionRef.current = null
    setPendingQuestionVersion(v => v + 1)
  }, [])

  // Derive pendingCodingAgentQuestion from ref + version counter for reactivity
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const _questionVersion = pendingQuestionVersion  // subscribe to state changes
  const pendingCodingAgentQuestion = pendingCodingAgentQuestionRef.current

  return {
    sendToModel,
    composeAndSend,
    sendMessage,
    sendSparkFixMessage,
    sendIgniteMessage,
    abortControllersRef,
    pendingCodingAgentQuestion,
    answerCodingAgentQuestion,
  }
}
