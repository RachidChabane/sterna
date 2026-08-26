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
import type { Chat, ChatGroup, FileAttachment, ImageAttachment, Model, Message, MessageContentPart, Attachment, AttachmentLike, MessageAttachment } from '@/components/models/types'
import { llmApi, type CodingAgentQuestion } from '@/api/llm'
import { extractSparks } from '@/utils/sparkParser'
import { DEFAULT_PARAMETERS } from '@/components/models/constants'
import { getUserFriendlyErrorMessage } from '@/utils/errorMessages'
import { isPDFFile, isOfficeFile } from '@/utils/fileUtils'
import { useUsageQuotaStore } from '@/store/usageQuotaStore'
import { conversationsAPI, type CreateMessageRequest } from '@/api/conversations'
import { type AssetReference } from '@/api/assets'
import { sparksAPI } from '@/api/sparks'
import { useArtifactsPanelStore } from '@/store/artifactsPanelStore'
import { codeSessionApi } from '@/api/codeSession'
import { useSettingsStore } from '@/store/settingsStore'
import useModelStore from '@/store/modelStore'
import type { ModelCatalogEntry } from '@/types/models'
import type { ApiMessage, SetChatGroups, ToastFn } from './messageSending/types'
import { buildUnsupportedAttachmentsMessage, uploadAttachmentsAsAssets } from './messageSending/attachmentAssets'
import { prepareApiMessagesWithAttachments } from './messageSending/attachmentPreparation'
import { buildLLMRequestPayload, type SendToModelOptions } from './messageSending/requestPayload'
import { createStreamAccumulator } from './messageSending/streamAccumulator'
import { cleanupStreamingSteps } from './messageSending/streamingStepHelpers'
import { buildPersistedSteps } from './messageSending/persistedSteps'
import { buildStreamCallbacks } from './messageSending/streamCallbacks'
import { useConversationTitleGeneration } from './messageSending/useConversationTitleGeneration'

interface UseMessageSendingProps {
  chats: Chat[]
  activeGroupId: string
  chatGroups: ChatGroup[]
  setChatGroups: SetChatGroups
  attachments: Attachment[]
  setAttachments: React.Dispatch<React.SetStateAction<Attachment[]>>
  toast: ToastFn
  isAuthenticated: boolean
  openModal: (variant: string, returnPath: string) => void
  getAuthModalVariant: () => string
}

interface UseMessageSendingReturn {
  sendToModel: (chatId: string, model: Model, messages: Message[], options?: SendToModelOptions) => Promise<void>
  composeAndSend: (targetChatIds: string[], content: string, localAttachments: AttachmentLike[], isToolContinuation?: boolean) => Promise<void>
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
      prevGroups.map((group: ChatGroup) =>
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
    let uploadedFiles: File[] = []
    let workspaceAssets: { asset_id: string; filename: string }[] = []
    if (lastApiUserIndex !== undefined && lastStateUserMsg) {
      // Only await when attachment prep actually went async (see prepareApiMessagesWithAttachments) —
      // awaiting an already-resolved value would still cost a microtask tick and delay dispatch.
      const maybePrepared = prepareApiMessagesWithAttachments(apiMessages, lastApiUserIndex, lastStateUserMsg, model)
      const prepared = maybePrepared instanceof Promise ? await maybePrepared : maybePrepared
      apiMessages = prepared.apiMessages
      hasFileAttachments = prepared.hasFileAttachments
      uploadedFiles = prepared.uploadedFiles
      workspaceAssets = prepared.workspaceAssets

      if (!prepared.hasSendableContent) {
        // No supported content; stop loading and bail out quickly
        setChatGroups(prev => prev.map((g: ChatGroup) => g.id === activeGroupId ? {
          ...g,
          chats: g.chats.map((c: Chat) => c.id === chatId ? { ...c, isLoading: false } : c),
          updatedAt: new Date(),
        } : g))
        return
      }
    }

    const requestPayload = buildLLMRequestPayload({
      model,
      apiMessages,
      parameters,
      streamResponsesSetting,
      hasFileAttachments,
      voiceConversationActive,
      options,
      activeGroupId,
      chatId,
      messageId,
      workspaceAssets,
    })

    // Streaming state accumulator - declared OUTSIDE the try block because the catch block
    // (abort persistence path) reads these; declaring them inside the try would
    // throw a ReferenceError at runtime when the catch runs.
    const streamingMessageTimestamp = new Date()
    const acc = createStreamAccumulator(streamingMessageTimestamp)

    // Use streaming for real-time responses
    try {
      // Create and store controller for this chat to allow cancellation
      const controller = new AbortController()
      abortControllersRef.current.set(chatId, controller)

      await llmApi.completeStream(
        requestPayload,
        buildStreamCallbacks({
          acc,
          setChatGroups,
          chats,
          activeGroupId,
          chatId,
          model,
          messageId,
          toast,
          pendingCodingAgentQuestionRef,
          setPendingQuestionVersion,
        }),
        { controller, uploadedFiles: uploadedFiles.length > 0 ? uploadedFiles : undefined }
      )

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
      let effectiveUsage = acc.messageMetadata?.usage ?? null
      let effectiveCost = acc.messageMetadata?.cost ?? undefined
      let effectivePromptCost = acc.messageMetadata?.prompt_cost ?? undefined
      let effectiveCompletionCost = acc.messageMetadata?.completion_cost ?? undefined

      // For aborted messages: use acc.lastUsageUpdate immediately (if available).
      // The precise OpenRouter query happens AFTER persistence (background).
      if (!effectiveUsage && wasAborted && acc.lastUsageUpdate) {
        effectiveUsage = acc.lastUsageUpdate.usage
        effectiveCost = acc.lastUsageUpdate.cost
        effectivePromptCost = acc.lastUsageUpdate.prompt_cost
        effectiveCompletionCost = acc.lastUsageUpdate.completion_cost
      }

      // Final update with duration and stop loading

      // Get sparks from tool results first (already persisted by backend)
      // Fall back to parsing from content (legacy method) or metadata
      // Extract outside setChatGroups callback so it's available for persistence
      const sparksFromTools = acc.accumulatedSparksFromTools
      const parsedSparks = extractSparks(acc.accumulatedContent)
      // Priority: 1) Sparks from create_spark tool, 2) Parsed from content, 3) From metadata
      const sparksToUse = sparksFromTools.length > 0
        ? sparksFromTools
        : (parsedSparks.length > 0 ? parsedSparks : (acc.messageMetadata?.sparks || []))
      const sparksAlreadyPersisted = sparksFromTools.length > 0 // Don't re-persist tool-created sparks

      // Auto-open the sparks side panel if sparks were created/updated via tools
      if (sparksFromTools.length > 0) {
        // Open the side panel with the most recently created/updated spark
        const latestSpark = sparksFromTools[sparksFromTools.length - 1]
        useArtifactsPanelStore.getState().openSparkInPanel(latestSpark.id)
      }

      setChatGroups(prevGroups =>
        prevGroups.map((group: ChatGroup) => {
          if (group.id !== activeGroupId) return group

          return {
            ...group,
            chats: group.chats.map((c: Chat) => {
              if (c.id !== chatId) return c

              return {
                ...c,
                messages: c.messages.map((m: Message) => {
                  if (m.timestamp === acc.streamingMessageTimestamp) {
                    // Clear any stuck isExecuting states and remove duplicate steps (safety cleanup)
                    const cleanedSteps = cleanupStreamingSteps(m.steps || [])

                    const updatedMessage = {
                      ...m,
                      content: acc.accumulatedContent,
                      reasoning_content: acc.accumulatedReasoning || m.reasoning_content,
                      web_sources: acc.accumulatedWebSources.length > 0 ? acc.accumulatedWebSources : m.web_sources,
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
                      ...(acc.messageMetadata?.finish_reason && { finish_reason: wasAborted ? 'cancelled' : acc.messageMetadata.finish_reason }),
                      ...(wasAborted && { is_stopped: true }),
                      // Add sparks (interactive React components)
                      ...(sparksToUse.length > 0 && { sparks: sparksToUse }),
                      // Add Sterna routing info (auto-router resolved model)
                      ...(acc.sternaRouteData && { sterna_route: acc.sternaRouteData }),
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
      // Use acc.totalContentForPersistence which never gets reset (unlike acc.accumulatedContent which resets after tool executions)
      const contentToPersist = acc.totalContentForPersistence || acc.accumulatedContent
      

      // Persist if there's text content OR tool executions (image generation may have minimal text)
      if (contentToPersist.trim() || acc.allToolExecutions.length > 0) {
        // Django DecimalField has max_digits=10, decimal_places=6
        // Round to 6 decimal places to avoid floating-point precision issues
        const costValue = effectiveCost !== undefined
          ? parseFloat(String(effectiveCost)).toFixed(6)
          : undefined

        // Build the message payload - only include defined fields
        const messagePayload: CreateMessageRequest = {
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
        // Use the tracked interleaved steps for persistence: text -> tool_executions -> text -> ...
        // This ensures the same display structure after reload as during streaming
        const persistedSteps = buildPersistedSteps(acc.accumulatedReasoning, acc.accumulatedSteps, { filterIncomplete: false })

        // Only include steps if there are any
        if (persistedSteps.length > 0) {
          messagePayload.steps = persistedSteps
        }

        // Include web sources in metadata for persistence
        if (acc.accumulatedWebSources.length > 0) {
          messagePayload.metadata = {
            ...(messagePayload.metadata || {}),
            web_sources: acc.accumulatedWebSources
          }
        }

        conversationsAPI.createMessage(activeGroupId, chatId, messagePayload).then((createdMessage) => {
          if (wasAborted && acc.generationId && createdMessage?.id) {
            // Query ALL generation IDs for comprehensive abort billing
            // Each iteration of the LLM tool loop has its own generation ID
            const idsToQuery = acc.generationIds.length > 0 ? acc.generationIds : [acc.generationId]
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

              const billingUpdate = {
                prompt_tokens: totalGenPrompt,
                completion_tokens: totalGenCompletion,
                cost: totalGenCost.toFixed(6),
              }
              // Patch DB
              conversationsAPI.updateMessage(activeGroupId, chatId, createdMessage.id, billingUpdate).catch(() => {})
              // Update React state so billing shows in UI immediately
              setChatGroups(prevGroups =>
                prevGroups.map((group: ChatGroup) => {
                  if (group.id !== activeGroupId) return group
                  return {
                    ...group,
                    chats: group.chats.map((c: Chat) => {
                      if (c.id !== chatId) return c
                      return {
                        ...c,
                        messages: c.messages.map((m: Message) => {
                          if (m.timestamp !== acc.streamingMessageTimestamp) return m
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

    } catch (error) {
      // Clean up controller on error
      abortControllersRef.current.delete(chatId)

      console.error(`[sendToModel] Error for ${model.name}:`, error)

      // Check if it was an abort
      if (error instanceof Error && (error.name === 'AbortError' || error.message.includes('aborted'))) {

        // Save partial content to DB immediately (billing data will be patched in background)
        const contentToPersist = acc.totalContentForPersistence || acc.accumulatedContent
        if (contentToPersist.trim() || acc.allToolExecutions.length > 0) {
          // Use acc.lastUsageUpdate for immediate persistence (available from completed iterations)
          const messagePayload: CreateMessageRequest = {
            role: 'assistant',
            content: contentToPersist,
            model_id: model.model_id,
            model_provider: model.provider,
            is_stopped: true,
            ...(acc.lastUsageUpdate && {
              prompt_tokens: acc.lastUsageUpdate.usage.prompt_tokens,
              completion_tokens: acc.lastUsageUpdate.usage.completion_tokens,
              cost: parseFloat(String(acc.lastUsageUpdate.cost)).toFixed(6),
            }),
          }

          // Build steps (reuse same logic as onDone path); a tool call may still be
          // mid-flight on the abort path, so incomplete executions are dropped.
          const persistedSteps = buildPersistedSteps(acc.accumulatedReasoning, acc.accumulatedSteps, { filterIncomplete: true })
          if (persistedSteps.length > 0) messagePayload.steps = persistedSteps
          if (acc.accumulatedWebSources.length > 0) {
            messagePayload.metadata = { web_sources: acc.accumulatedWebSources }
          }

          try {
            const createdMessage = await conversationsAPI.createMessage(activeGroupId, chatId, messagePayload)
            // Query OpenRouter in background for precise billing, then PATCH
            if (acc.generationId && createdMessage?.id) {
              llmApi.getGenerationUsage(acc.generationId).then((genData) => {
                const prior = acc.lastUsageUpdate
                const billingUpdate = {
                  prompt_tokens: (prior?.usage.prompt_tokens || 0) + genData.usage.prompt_tokens,
                  completion_tokens: (prior?.usage.completion_tokens || 0) + genData.usage.completion_tokens,
                  cost: ((prior?.cost || 0) + (genData.cost || 0)).toFixed(6),
                }
                // Patch DB
                conversationsAPI.updateMessage(activeGroupId, chatId, createdMessage.id, billingUpdate).catch(
                  e => console.warn('[sendToModel] Failed to patch billing data:', e)
                )
                // Update React state so billing shows in UI immediately
                setChatGroups(prevGroups =>
                  prevGroups.map((group: ChatGroup) => {
                    if (group.id !== activeGroupId) return group
                    return {
                      ...group,
                      chats: group.chats.map((c: Chat) => {
                        if (c.id !== chatId) return c
                        return {
                          ...c,
                          messages: c.messages.map((m: Message) => {
                            if (m.timestamp !== acc.streamingMessageTimestamp) return m
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
          prevGroups.map((group: ChatGroup) =>
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
        prevGroups.map((group: ChatGroup) => {
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

  // Generate a conversation title based on the first user message (async, non-blocking)
  const generateConversationTitle = useConversationTitleGeneration({ activeGroupId, setChatGroups })

  const composeAndSend = useCallback(async (
    targetChatIds: string[],
    content: string,
    localAttachments: AttachmentLike[],
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

    const imageAttachments = localAttachments.filter((a): a is ImageAttachment => a.type === 'image')
    const fileAttachments = localAttachments.filter((a): a is FileAttachment => a.type === 'file')
    const pdfAttachments = fileAttachments.filter(f => f.base64 && !f.textContent && f.file && isPDFFile(f.file))
    const officeAttachments = fileAttachments.filter(f => f.base64 && !f.textContent && f.file && isOfficeFile(f.file))
    const hasImages = imageAttachments.length > 0
    const hasPDFs = pdfAttachments.length > 0
    const hasOfficeFiles = officeAttachments.length > 0
    const hasText = content.trim().length > 0
    const timestamp = new Date()

    let updatedChats: Chat[] = []

    setChatGroups(prevGroups =>
      prevGroups.map((group: ChatGroup) => {
        if (group.id !== activeGroupId) return group

        const updatedGroupChats = group.chats.map((chat: Chat) => {
          if (!targetChatIds.includes(chat.id)) return chat
          if (chat.disabled || chat.model === null) return chat

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
              // Reconstructed (post-redirect) attachments never carry a real File; a freshly-composed one always does.
              attachments: localAttachments.length > 0 ? localAttachments as MessageAttachment[] : undefined,
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
      let messageContent: string | Array<{ type: 'text'; text: string } | AssetReference> = content
      if (assetRefs.length > 0) {
        // Store as multipart content: text + asset references
        const parts: Array<{ type: 'text'; text: string } | AssetReference> = []
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
    const activeGroup = chatGroups.find((g: ChatGroup) => g.id === activeGroupId)
    const isFirstMessage = !isToolContinuation &&
      activeGroup &&
      !activeGroup.isCustomName &&
      !activeGroup.chats.some((c) => c.messages.some((m) => m.role === 'user'))

    // Send to targets in parallel using updated state
    const enabledChats = updatedChats.filter(c => targetChatIds.includes(c.id) && c.model !== null && !c.disabled)

    // Track each model as recently used (for "Recent Chat Models" section in dropdown)
    enabledChats.forEach(c => {
      if (c.model) {
        // Model and ModelCatalogEntry are independently-typed views of the same backend record.
        addRecentChatModel(c.model.model_id, c.model as ModelCatalogEntry)
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
    const enabledIds = chats.filter(c => c.model !== null && !c.disabled).map(c => c.id)
    if (enabledIds.length === 0) return

    // Take a snapshot of current attachments with enriched metadata for serialization survival
    const currentAttachments = attachments.map(att => ({
      ...att,
      // Extract File metadata at root level so they survive JSON serialization
      fileName: att.file.name,
      fileType: att.file.type,
      fileSize: att.file.size,
    }))

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
      prevGroups.map((group: ChatGroup) =>
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
      prevGroups.map((group: ChatGroup) =>
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
        setChatGroups((prev) =>
          prev.map((group: ChatGroup) =>
            group.id !== activeGroupId ? group : {
              ...group,
              chats: group.chats.map((c: Chat) => ({
                ...c,
                messages: c.messages.map((m: Message) => ({
                  ...m,
                  sparks: m.sparks?.map((s) =>
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
