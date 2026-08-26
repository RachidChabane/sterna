/**
 * Per-chat callback factories for ModelComparisonPage.
 *
 * Each `getXHandler(chatId)` lazily creates and caches a stable function
 * reference per chat id in a Map, so passing `onSendMessage={getSendMessageHandler(chat.id)}`
 * down to a memoized chat card never changes identity across renders for a
 * chat whose own state hasn't changed - only typing in ONE chat's input
 * re-renders that chat, not every chat in the comparison.
 *
 * The Maps are cleared synchronously DURING render (not in an effect) when
 * the underlying mutation function (composeAndSend / updateChatModel /
 * updateChatMessages) changes identity, so a get*Handler call within the
 * same render already returns a fresh handler instead of a stale one built
 * on a previous closure.
 */
import { useCallback, useRef } from 'react'
import type { RefObject } from 'react'
import { llmApi } from '@/api/llm'
import { buildTextFromTextAttachments } from '@/utils/tokenEstimate'
import type { useToast } from '@/hooks/use-toast'
import type {
  Attachment,
  Chat,
  FileAttachment,
  ImageAttachment,
  Message,
  Model,
  ModelParameters,
  ToolExecutedHandler,
} from '../types'
import type { ModelCostEstimate } from '@/api/llm'

interface UseChatHandlerMapsParams {
  chats: Chat[]
  chatsRef: RefObject<Chat[]>
  composeAndSend: (chatIds: string[], content: string, attachments: Attachment[]) => Promise<void>
  sendToModel: (chatId: string, model: Model, messages: Message[]) => void
  updateChatModel: (chatId: string, model: Model) => void
  updateChatMessages: (chatId: string, messages: Message[]) => void
  updateChatParameters: (chatId: string, params: ModelParameters) => void
  updateChatDisabled: (chatId: string, value: boolean) => void
  updateChatHidden: (chatId: string, value: boolean) => void
  moveLeft: (chatId: string) => void
  moveRight: (chatId: string) => void
  clearChat: (chatId: string, deleteWorkspace?: boolean) => void
  cancelChat: (chatId: string) => void
  toast: ReturnType<typeof useToast>['toast']
  onRequestRemoveChat: (chatId: string) => void
}

export function useChatHandlerMaps({
  chats,
  chatsRef,
  composeAndSend,
  sendToModel,
  updateChatModel,
  updateChatMessages,
  updateChatParameters,
  updateChatDisabled,
  updateChatHidden,
  moveLeft,
  moveRight,
  clearChat,
  cancelChat,
  toast,
  onRequestRemoveChat,
}: UseChatHandlerMapsParams) {
  const sendMessageHandlers = useRef(new Map<string, (content: string, localAttachments?: Attachment[]) => Promise<void>>())
  const modelSelectHandlers = useRef(new Map<string, (model: Model) => void>())
  const updateMessagesHandlers = useRef(new Map<string, (messages: Message[]) => void>())
  const removeHandlers = useRef(new Map<string, () => void>())
  const estimateCostHandlers = useRef(new Map<string, (text: string, atts?: Attachment[]) => Promise<Omit<ModelCostEstimate, 'model_id'> | null>>())

  // Track previous function references to detect changes synchronously
  // IMPORTANT: This must clear the cache DURING render, not in an effect
  // Otherwise, get*Handler returns stale handlers before the effect runs
  // This fixes issues like voice mode not being passed when the overlay opens
  const prevComposeAndSendRef = useRef(composeAndSend)
  if (prevComposeAndSendRef.current !== composeAndSend) {
    sendMessageHandlers.current.clear()
    prevComposeAndSendRef.current = composeAndSend
  }

  // Clear model select handlers synchronously when updateChatModel changes
  // This is CRITICAL: without this, changing one chat's model would affect other chats
  // because the old handlers capture stale closure values
  const prevUpdateChatModelRef = useRef(updateChatModel)
  if (prevUpdateChatModelRef.current !== updateChatModel) {
    modelSelectHandlers.current.clear()
    prevUpdateChatModelRef.current = updateChatModel
  }

  // Clear update messages handlers synchronously when updateChatMessages changes
  const prevUpdateChatMessagesRef = useRef(updateChatMessages)
  if (prevUpdateChatMessagesRef.current !== updateChatMessages) {
    updateMessagesHandlers.current.clear()
    prevUpdateChatMessagesRef.current = updateChatMessages
  }

  // Get or create stable handler for each chat (sends to single chat only)
  const getSendMessageHandler = useCallback((chatId: string) => {
    if (!sendMessageHandlers.current.has(chatId)) {
      sendMessageHandlers.current.set(chatId, async (content: string, localAttachments?: Attachment[]) => {
        await composeAndSend([chatId], content, localAttachments || [])
      })
    }
    return sendMessageHandlers.current.get(chatId)!
  }, [composeAndSend])

  // Broadcast handler for multi-chat mode: sends to ALL enabled chats
  const sendToAllChatsHandler = useCallback(async (content: string, localAttachments?: Attachment[]) => {
    const enabledIds = chats.filter(c => c.model !== null && !c.disabled).map(c => c.id)
    if (enabledIds.length === 0) {
      toast({
        title: 'No model selected',
        description: 'Please select at least one model to send a message.',
        variant: 'destructive'
      })
      return
    }
    await composeAndSend(enabledIds, content, localAttachments || [])
  }, [chats, composeAndSend, toast])

  const getModelSelectHandler = useCallback((chatId: string) => {
    if (!modelSelectHandlers.current.has(chatId)) {
      modelSelectHandlers.current.set(chatId, (model: Model) => {
        // Only update the chat's model, don't affect global model selection
        updateChatModel(chatId, model)
      })
    }
    return modelSelectHandlers.current.get(chatId)!
  }, [updateChatModel])

  const getUpdateMessagesHandler = useCallback((chatId: string) => {
    if (!updateMessagesHandlers.current.has(chatId)) {
      updateMessagesHandlers.current.set(chatId, (messages: Message[]) => {
        updateChatMessages(chatId, messages)
      })
    }
    return updateMessagesHandlers.current.get(chatId)!
  }, [updateChatMessages])

  const getRemoveHandler = useCallback((chatId: string) => {
    if (!removeHandlers.current.has(chatId)) {
      removeHandlers.current.set(chatId, () => {
        onRequestRemoveChat(chatId)
      })
    }
    return removeHandlers.current.get(chatId)!
  }, [onRequestRemoveChat])

  // Handle cost estimation for individual chat in independent mode (memoized)
  const handleEstimateCostForChat = useCallback(async (chatId: string, text: string, localAttachments: Attachment[] = []) => {
    const chat = chats.find(c => c.id === chatId)
    if (!chat?.model) return null
    try {
      const filesText = buildTextFromTextAttachments(localAttachments)
      const filesMeta = (localAttachments || [])
        .filter((a): a is FileAttachment => a.type === 'file')
        .map((f) => ({ filename: f.file?.name || 'file', mime: f.file?.type || undefined, size: f.file?.size || undefined }))
      const imagesMeta = (localAttachments || [])
        .filter((a): a is ImageAttachment => a.type === 'image')
        .map((img) => ({ mime: img.file?.type || undefined, size: img.file?.size || undefined }))
      const response = await llmApi.estimateBatchCost({
        model_ids: [chat.model.model_id],
        prompt_text: text + filesText,
        typed_text: text,
        files_text: filesText,
        features_by_model: {
          [chat.model.model_id]: {
            system_prompt: chat.parameters?.system_prompt || '',
            enable_mcp_tools: chat.parameters?.enable_mcp_tools || false,
            enable_reasoning: chat.parameters?.enable_reasoning || false,
            enable_file_tools: chat.parameters?.enable_file_tools || false,
          }
        },
        files: filesMeta,
        images: imagesMeta,
        max_new_tokens_by_model: chat.parameters?.max_tokens
          ? { [chat.model.model_id]: chat.parameters.max_tokens }
          : undefined,
      })
      const data = {
        ...response.data,
        total_cost: typeof response.data.total_cost === 'string' ? parseFloat(response.data.total_cost) : response.data.total_cost,
        costs: response.data.costs.map((c) => ({ ...c, cost: typeof c.cost === 'string' ? parseFloat(c.cost) : c.cost })),
      }
      if (data.costs && data.costs.length > 0) {
        return {
          cost: data.costs[0].cost,
          prompt_tokens: data.costs[0].prompt_tokens,
          completion_tokens: data.costs[0].completion_tokens,
          model_name: data.costs[0].model_name,
        }
      }
      return null
    } catch (error) {
      throw error
    }
  }, [chats])

  const getEstimateCostHandler = useCallback((chatId: string) => {
    if (!estimateCostHandlers.current.has(chatId)) {
      estimateCostHandlers.current.set(chatId, (text: string, atts?: Attachment[]) => {
        return handleEstimateCostForChat(chatId, text, atts)
      })
    }
    return estimateCostHandlers.current.get(chatId)!
  }, [handleEstimateCostForChat])

  const moveLeftHandlers = useRef(new Map<string, () => void>())
  const moveRightHandlers = useRef(new Map<string, () => void>())
  const parametersChangeHandlers = useRef(new Map<string, (params: ModelParameters) => void>())
  const toggleDisabledHandlers = useRef(new Map<string, (value: boolean) => void>())
  const toggleHiddenHandlers = useRef(new Map<string, (value: boolean) => void>())
  const clearChatHandlers = useRef(new Map<string, (deleteWorkspace?: boolean) => void>())
  const cancelChatHandlers = useRef(new Map<string, () => void>())

  const getMoveLeftHandler = useCallback((chatId: string) => {
    if (!moveLeftHandlers.current.has(chatId)) {
      moveLeftHandlers.current.set(chatId, () => moveLeft(chatId))
    }
    return moveLeftHandlers.current.get(chatId)!
  }, [moveLeft])

  const getMoveRightHandler = useCallback((chatId: string) => {
    if (!moveRightHandlers.current.has(chatId)) {
      moveRightHandlers.current.set(chatId, () => moveRight(chatId))
    }
    return moveRightHandlers.current.get(chatId)!
  }, [moveRight])

  const getParametersChangeHandler = useCallback((chatId: string) => {
    if (!parametersChangeHandlers.current.has(chatId)) {
      parametersChangeHandlers.current.set(chatId, (params: ModelParameters) => updateChatParameters(chatId, params))
    }
    return parametersChangeHandlers.current.get(chatId)!
  }, [updateChatParameters])

  const getToggleDisabledHandler = useCallback((chatId: string) => {
    if (!toggleDisabledHandlers.current.has(chatId)) {
      toggleDisabledHandlers.current.set(chatId, (value: boolean) => updateChatDisabled(chatId, value))
    }
    return toggleDisabledHandlers.current.get(chatId)!
  }, [updateChatDisabled])

  const getToggleHiddenHandler = useCallback((chatId: string) => {
    if (!toggleHiddenHandlers.current.has(chatId)) {
      toggleHiddenHandlers.current.set(chatId, (value: boolean) => updateChatHidden(chatId, value))
    }
    return toggleHiddenHandlers.current.get(chatId)!
  }, [updateChatHidden])

  const getClearChatHandler = useCallback((chatId: string) => {
    if (!clearChatHandlers.current.has(chatId)) {
      clearChatHandlers.current.set(chatId, (deleteWorkspace?: boolean) => clearChat(chatId, deleteWorkspace))
    }
    return clearChatHandlers.current.get(chatId)!
  }, [clearChat])

  const getCancelChatHandler = useCallback((chatId: string) => {
    if (!cancelChatHandlers.current.has(chatId)) {
      cancelChatHandlers.current.set(chatId, () => cancelChat(chatId))
    }
    return cancelChatHandlers.current.get(chatId)!
  }, [cancelChat])

  const toolExecutedHandlers = useRef(new Map<string, ToolExecutedHandler>())

  const getToolExecutedHandler = useCallback((chatId: string) => {
    if (!toolExecutedHandlers.current.has(chatId)) {
      toolExecutedHandlers.current.set(chatId, (toolCallId: string, toolName: string, result: Record<string, unknown> | undefined) => {
        // Get current chat using ref to avoid stale closure issues in multi-chat parallel scenarios
        const currentChat = chatsRef.current.find(c => c.id === chatId)
        if (!currentChat) return

        // Add a "tool" message with the execution result (OpenAI format)
        // This message will be sent to the model but NOT displayed in the UI
        const toolMessage: Message = {
          role: 'tool',
          tool_call_id: toolCallId,
          content: JSON.stringify(result?.content),  // Send the raw tool result to the model
          timestamp: new Date(),
        }

        // Update messages to include the tool result
        const updatedMessages = [...currentChat.messages, toolMessage]

        // Update state with the tool message
        updateChatMessages(chatId, updatedMessages)

        // Continue the conversation immediately by sending the updated messages directly
        // We pass the messages explicitly to avoid async state issues
        if (currentChat.model) {
          sendToModel(chatId, currentChat.model, updatedMessages)
        }
      })
    }
    return toolExecutedHandlers.current.get(chatId)!
    // chatsRef is a stable ref identity (never changes), included only to
    // satisfy exhaustive-deps now that it crosses a hook-parameter boundary
  }, [updateChatMessages, sendToModel, chatsRef])

  return {
    getSendMessageHandler,
    sendToAllChatsHandler,
    getModelSelectHandler,
    getUpdateMessagesHandler,
    getRemoveHandler,
    getEstimateCostHandler,
    getMoveLeftHandler,
    getMoveRightHandler,
    getParametersChangeHandler,
    getToggleDisabledHandler,
    getToggleHiddenHandler,
    getClearChatHandler,
    getCancelChatHandler,
    getToolExecutedHandler,
  }
}
