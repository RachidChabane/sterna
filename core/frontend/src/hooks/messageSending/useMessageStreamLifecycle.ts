import { useRef, useCallback } from 'react'
import type { Chat, ChatGroup, Model, Message, MessageContentPart } from '@/components/models/types'
import { llmApi, type CodingAgentQuestion } from '@/api/llm'
import { extractSparks } from '@/utils/sparkParser'
import { DEFAULT_PARAMETERS } from '@/components/models/constants'
import { getUserFriendlyErrorMessage } from '@/utils/errorMessages'
import { conversationsAPI, type CreateMessageRequest } from '@/api/conversations'
import { sparksAPI } from '@/api/sparks'
import { useArtifactsPanelStore } from '@/store/artifactsPanelStore'
import { codeSessionApi } from '@/api/codeSession'
import type { ApiMessage, SetChatGroups, ToastFn } from './types'
import { prepareApiMessagesWithAttachments } from './attachmentPreparation'
import { buildLLMRequestPayload, type SendToModelOptions } from './requestPayload'
import { createStreamAccumulator } from './streamAccumulator'
import { cleanupStreamingSteps } from './streamingStepHelpers'
import { buildPersistedSteps } from './persistedSteps'
import { buildStreamCallbacks } from './streamCallbacks'

export interface UseMessageStreamLifecycleProps {
  chats: Chat[]
  activeGroupId: string
  setChatGroups: SetChatGroups
  toast: ToastFn
  streamResponsesSetting: boolean
  voiceConversationActive: boolean
  refreshQuotaAfterUsage: () => Promise<void>
  /** Owned by useCodingAgentQuestion; mutated here as an ask_user tool call arrives and resolves mid-stream. */
  pendingCodingAgentQuestionRef: React.MutableRefObject<CodingAgentQuestion | null>
  setPendingQuestionVersion: React.Dispatch<React.SetStateAction<number>>
}

export interface UseMessageStreamLifecycleReturn {
  sendToModel: (chatId: string, model: Model, messages: Message[], options?: SendToModelOptions) => Promise<void>
  abortControllersRef: React.MutableRefObject<Map<string, AbortController>>
}

/**
 * Owns one sendToModel call end to end: building the request payload,
 * streaming the response, accumulating content/reasoning/tool steps, and
 * persisting the resulting assistant message (including the abort and
 * error paths).
 */
export function useMessageStreamLifecycle({
  chats,
  activeGroupId,
  setChatGroups,
  toast,
  streamResponsesSetting,
  voiceConversationActive,
  refreshQuotaAfterUsage,
  pendingCodingAgentQuestionRef,
  setPendingQuestionVersion,
}: UseMessageStreamLifecycleProps): UseMessageStreamLifecycleReturn {
  // Track abort controllers for each chat to allow request cancellation
  const abortControllersRef = useRef<Map<string, AbortController>>(new Map())

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
  }, [chats, activeGroupId, setChatGroups, toast, streamResponsesSetting, voiceConversationActive, refreshQuotaAfterUsage, pendingCodingAgentQuestionRef, setPendingQuestionVersion])

  return { sendToModel, abortControllersRef }
}
