import type { Chat, ChatGroup, Message } from '@/components/models/types'
import type { CodingAgentQuestion, CodingAgentResult, CodingAgentStep } from '@/api/llm'
import type { StreamCallbacksContext } from './context'
import { CODING_AGENT_TOOLS } from '../constants'

/**
 * Builds the onCodingAgentStep / onCodingAgentCompleted / onCodingAgentQuestion
 * stream callbacks: progress and completion for the Coding Agent sub-flow (which
 * runs inside a coding_agent / plan_implementation / implement_plan / edit_plan
 * tool call), plus the ask_user question hand-off.
 */
export function buildCodingAgentCallbacks(ctx: StreamCallbacksContext) {
  const { acc, setChatGroups, activeGroupId, chatId, pendingCodingAgentQuestionRef, setPendingQuestionVersion } = ctx

  return {
  onCodingAgentStep: (step: CodingAgentStep) => {
    // Handle Coding Agent agent step progress
    acc.accumulatedCodingAgentSteps.push(step)

    // Also update acc.accumulatedSteps for persistence - find the coding_agent execution and update it
    for (const accStep of acc.accumulatedSteps) {
      if (accStep.type === 'tool_executions') {
        for (const exec of accStep.executions || []) {
          if (CODING_AGENT_TOOLS.has(exec.tool_call?.function?.name)) {
            exec.coding_agent_steps = [...acc.accumulatedCodingAgentSteps]
          }
        }
      }
    }

    // Update the message with Coding Agent steps (on the last tool_executions step for coding_agent)
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
              return {
                ...c,
                messages: c.messages.map((m: Message) => {
                  if (m.timestamp !== acc.streamingMessageTimestamp) return m

                  // Update coding_agent tool execution in steps with the new step
                  const steps = m.steps || []
                  const updatedSteps = steps.map((s) => {
                    if (s.type === 'tool_executions') {
                      return {
                        ...s,
                        executions: s.executions?.map((exec) => {
                          if (CODING_AGENT_TOOLS.has(exec.tool_call?.function?.name)) {
                            return {
                              ...exec,
                              coding_agent_steps: [...acc.accumulatedCodingAgentSteps]
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
    acc.accumulatedCodingAgentResult = result

    // Also update acc.accumulatedSteps for persistence - store the final result
    for (const accStep of acc.accumulatedSteps) {
      if (accStep.type === 'tool_executions') {
        for (const exec of accStep.executions || []) {
          if (CODING_AGENT_TOOLS.has(exec.tool_call?.function?.name)) {
            // Use result.steps if available and has more content than accumulated steps
            const finalSteps = (result.steps && result.steps.length > acc.accumulatedCodingAgentSteps.length)
              ? result.steps
              : acc.accumulatedCodingAgentSteps
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
              return {
                ...c,
                messages: c.messages.map((m: Message) => {
                  if (m.timestamp !== acc.streamingMessageTimestamp) return m

                  // Update coding_agent tool execution in steps with the result
                  const steps = m.steps || []
                  const updatedSteps = steps.map((s) => {
                    if (s.type === 'tool_executions') {
                      return {
                        ...s,
                        executions: s.executions?.map((exec) => {
                          if (CODING_AGENT_TOOLS.has(exec.tool_call?.function?.name)) {
                            // Use result.steps if available and has more content than accumulated steps
                            // This ensures we show the complete steps from the final result
                            const finalSteps = (result.steps && result.steps.length > acc.accumulatedCodingAgentSteps.length)
                              ? result.steps
                              : acc.accumulatedCodingAgentSteps
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
  }
}
