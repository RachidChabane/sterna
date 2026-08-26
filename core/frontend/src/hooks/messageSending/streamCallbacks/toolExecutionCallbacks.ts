import type { Chat, Message, ChatGroup, ToolCall, ToolCallApproval, ToolResult } from '@/components/models/types'
import { codeSessionApi } from '@/api/codeSession'
import { useProjectPanelStore } from '@/store/projectPanelStore'
import type { StreamCallbacksContext } from './context'
import { extractSparksFromToolResults, buildExecutionsFromToolResults } from '../toolResultProcessing'

/**
 * Builds the onToolCallRequest / onFileToolExecuting / onFileToolExecuted stream
 * callbacks: the tool-call lifecycle from an approval request through execution
 * start to completed results (including spark extraction and the plan/implement
 * side-panel auto-open).
 */
export function buildToolExecutionCallbacks(ctx: StreamCallbacksContext) {
  const { acc, setChatGroups, chats, activeGroupId, chatId, model, messageId } = ctx

  return {
  onToolCallRequest: (approvals: ToolCallApproval[], toolCalls: ToolCall[]) => {
    // Handle tool call approval requests from the model


    setChatGroups(prevGroups =>
      prevGroups.map((group: ChatGroup) => {
        if (group.id !== activeGroupId) return group

        return {
          ...group,
          chats: group.chats.map((c: Chat) => {
            if (c.id !== chatId) return c

            // Check if we already have a streaming message
            const hasStreamingMessage = c.messages.some((m: Message) =>
              m.role === 'assistant' && m.timestamp === acc.streamingMessageTimestamp
            )

            if (hasStreamingMessage) {
              // Update existing streaming message with tool calls and pending approvals
              return {
                ...c,
                messages: c.messages.map((m: Message) =>
                  m.timestamp === acc.streamingMessageTimestamp
                    ? {
                        ...m,
                        content: acc.accumulatedContent,
                        reasoning_content: acc.accumulatedReasoning || m.reasoning_content,
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
                content: acc.accumulatedContent,
                timestamp: acc.streamingMessageTimestamp,
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

  onFileToolExecuting: (toolCalls: ToolCall[]) => {
    // Handle file tool execution START - show loading state
    // Also handles UPDATE when placeholder is replaced with real tool call data
    const startTime = Date.now()

    // Check if this is an update to a placeholder (id: "loading" -> real id)
    const isPlaceholderUpdate = toolCalls.length > 0 &&
      toolCalls[0].id !== 'loading' &&
      acc.accumulatedSteps.some((s) =>
        s.type === 'tool_executions' &&
        s.isExecuting === true &&
        s.executions?.some((e) => e.tool_call?.id === 'loading')
      )

    // Mark the boundary for the next text step - any text after this tool execution
    // should start a new text step from this point in acc.accumulatedContent
    if (!isPlaceholderUpdate) {
      acc.currentTextStepStartIndex = acc.accumulatedContent.length
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

    // Track in acc.accumulatedSteps for persistence
    if (isPlaceholderUpdate) {
      // Find and update the placeholder step instead of adding new one
      const placeholderIndex = acc.accumulatedSteps.findIndex((s) =>
        s.type === 'tool_executions' &&
        s.isExecuting === true &&
        s.executions?.some((e) => e.tool_call?.id === 'loading')
      )
      if (placeholderIndex !== -1) {
        // Preserve original startTime from placeholder
        const placeholderStep = acc.accumulatedSteps[placeholderIndex]
        const originalStartTime = (placeholderStep.type === 'tool_executions' ? placeholderStep.executions?.[0]?.startTime : undefined) || startTime
        executions.forEach(e => e.startTime = originalStartTime)
        acc.accumulatedSteps[placeholderIndex] = { type: 'tool_executions', executions: [...executions], isExecuting: true }
      }
    } else {
      acc.accumulatedSteps.push({ type: 'tool_executions', executions: [...executions], isExecuting: true })
    }

    

    // Update the message with file tool executions as a new step (loading state)
    setChatGroups(prevGroups =>
      prevGroups.map((group: ChatGroup) => {
        if (group.id !== activeGroupId) return group

        return {
          ...group,
          chats: group.chats.map((c: Chat) => {
            if (c.id !== chatId) return c

            // Check if we already have a streaming message
            const hasStreamingMessage = c.messages.some((m: Message) =>
              m.role === 'assistant' && m.timestamp === acc.streamingMessageTimestamp
            )

            if (hasStreamingMessage) {
              // Add tool executions as a new step (loading state)
              // Or update placeholder step with real tool call data
              // Also finalize any ongoing reasoning step
              return {
                ...c,
                messages: c.messages.map((m: Message) => {
                  if (m.timestamp !== acc.streamingMessageTimestamp) return m

                  const steps = m.steps || []
                  const lastStep = steps[steps.length - 1]

                  // Check if we're updating a placeholder step (id: "loading" -> real id)
                  const placeholderStepIndex = steps.findIndex((s) =>
                    s.type === 'tool_executions' &&
                    s.isExecuting === true &&
                    s.executions?.some((e) => e.tool_call?.id === 'loading')
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
                    acc.previousReasoningContent = acc.accumulatedReasoning
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
                content: acc.accumulatedContent,
                timestamp: acc.streamingMessageTimestamp,
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

  onFileToolExecuted: (toolCalls: ToolCall[], results: ToolResult[]) => {
    // Handle file tool execution COMPLETED - update with results

    // Get tool call IDs for matching against executing steps
    const executedToolCallIds = new Set(toolCalls.map(tc => tc.id))

    // Extract sparks from create_spark/update_spark tool results (already persisted by backend)
    acc.accumulatedSparksFromTools.push(...extractSparksFromToolResults(toolCalls, results))

    // Build file_tool_executions array for UI display (coding_agent tools get their
    // steps/result attached from coding_agent_data)
    const executions = buildExecutionsFromToolResults(toolCalls, results, acc.accumulatedCodingAgentSteps, acc.accumulatedCodingAgentResult)

    // Auto-open side panel when plan/implement tools succeed
    toolCalls.forEach((tc, idx) => {
      const result = results[idx] as { success?: boolean; data?: { plan_id: string } } | null
      const planId = result?.success ? result.data?.plan_id : undefined
      if (tc.function?.name === 'plan_implementation' && planId) {
        codeSessionApi.getPlan(planId).then((res) => {
          const store = useProjectPanelStore.getState()
          store.addPlan(res.data)
          store.selectPlan(planId)
          store.openPanel('plans')
        }).catch(console.error)
      }
      if (tc.function?.name === 'implement_plan' && planId) {
        // Fetch the updated plan (with implementation_branch, status, etc.)
        const store = useProjectPanelStore.getState()
        codeSessionApi.getPlan(planId).then((res) => {
          store.updatePlan(planId, res.data)
          store.selectPlan(planId)
          store.openPanel('plans')
        }).catch(console.error)
      }
    })

    // Track all tool executions for persistence
    acc.allToolExecutions = [...acc.allToolExecutions, ...executions]

    // Update the matching tool_executions step in acc.accumulatedSteps with results
    // Match by tool_call.id to avoid race conditions with multiple concurrent tool calls
    let matchingStepIndex = acc.accumulatedSteps.findLastIndex(
      (s) => s.type === 'tool_executions' && s.isExecuting === true &&
        s.executions?.some((e) => executedToolCallIds.has(e.tool_call?.id))
    )

    // Fallback: if no match by real ID, try to find placeholder step (id: "loading")
    // This handles race condition where update event hasn't been processed yet
    if (matchingStepIndex === -1) {
      matchingStepIndex = acc.accumulatedSteps.findLastIndex(
        (s) => s.type === 'tool_executions' && s.isExecuting === true &&
          s.executions?.some((e) => e.tool_call?.id === 'loading')
      )
    }

    if (matchingStepIndex !== -1) {
      acc.accumulatedSteps[matchingStepIndex] = {
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
      (m: Message) => m.role === 'assistant' && m.timestamp === acc.streamingMessageTimestamp
    )
    const currentSteps = currentMessage?.steps || []
    let matchingToolExecIndex = currentSteps.findLastIndex(
      (s) => s.type === 'tool_executions' && s.isExecuting === true &&
        s.executions?.some((e) => executedToolCallIds.has(e.tool_call?.id))
    )

    // Fallback: if no match by real ID, try to find placeholder step (id: "loading")
    if (matchingToolExecIndex === -1) {
      matchingToolExecIndex = currentSteps.findLastIndex(
        (s) => s.type === 'tool_executions' && s.isExecuting === true &&
          s.executions?.some((e) => e.tool_call?.id === 'loading')
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
    const contentBeforeToolExec = acc.accumulatedContent
    acc.accumulatedContent = ''
    // Also reset the text step start index since acc.accumulatedContent is reset
    acc.currentTextStepStartIndex = 0
    

    // Helper function to update the chat groups (no timing logic inside)
    const updateWithResults = () => {
      setChatGroups(prevGroups =>
        prevGroups.map((group: ChatGroup) => {
          if (group.id !== activeGroupId) return group

          return {
            ...group,
            chats: group.chats.map((c: Chat) => {
              if (c.id !== chatId) return c

              // Check if we already have a streaming message
              const hasStreamingMessage = c.messages.some((m: Message) =>
                m.role === 'assistant' && m.timestamp === acc.streamingMessageTimestamp
              )

              if (hasStreamingMessage) {
                // Replace the loading step with completed results
                return {
                  ...c,
                  messages: c.messages.map((m: Message) => {
                    if (m.timestamp !== acc.streamingMessageTimestamp) return m

                    const steps = m.steps || []
                    // Find and replace the tool_executions step that matches by tool_call.id
                    // This prevents race conditions when multiple tools execute concurrently
                    let matchingStepIndex = steps.findLastIndex(
                      (s) => s.type === 'tool_executions' && s.isExecuting === true &&
                        s.executions?.some((e) => executedToolCallIds.has(e.tool_call?.id))
                    )

                    // Fallback: if no match by real ID, try to find placeholder step (id: "loading")
                    if (matchingStepIndex === -1) {
                      matchingStepIndex = steps.findLastIndex(
                        (s) => s.type === 'tool_executions' && s.isExecuting === true &&
                          s.executions?.some((e) => e.tool_call?.id === 'loading')
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
                        steps.flatMap((s) =>
                          s.type === 'tool_executions' && !s.isExecuting
                            ? s.executions?.map((e) => e.tool_call?.id) || []
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
                      (m.file_tool_executions || []).map((e) => e.tool_call?.id)
                    )
                    const newExecutions = executions.filter((e) => !existingExecIds.has(e.tool_call?.id))

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
                  timestamp: acc.streamingMessageTimestamp,
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
  }
}
