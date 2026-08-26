import type { Chat, ChatGroup, Message } from '@/components/models/types'
import type { WebSource } from '@/api/llm'
import type { StreamCallbacksContext } from './context'
import { getReasoningDelta } from '../streamingStepHelpers'

/**
 * Builds the onContent / onReasoning / onWebSources / onImage stream callbacks:
 * the handlers that accumulate a model's raw content, reasoning, citations, and
 * generated images into the live streaming message.
 */
export function buildMessageContentCallbacks(ctx: StreamCallbacksContext) {
  const { acc, setChatGroups, activeGroupId, chatId, model, messageId } = ctx

  return {
  onContent: (content: string) => {
    // Accumulate content as it streams in (keep same message throughout)
    acc.accumulatedContent += content
    acc.totalContentForPersistence += content // Also track for persistence (never reset)

    // Get the content for the current text step (from acc.currentTextStepStartIndex to end)
    const currentTextStepContent = acc.accumulatedContent.slice(acc.currentTextStepStartIndex)

    // Update acc.accumulatedSteps for persistence - track the interleaved structure
    const lastAccStep = acc.accumulatedSteps[acc.accumulatedSteps.length - 1]
    if (lastAccStep?.type === 'text') {
      // Update existing text step
      lastAccStep.content = currentTextStepContent
    } else {
      // Create new text step (first text or after tool_executions)
      acc.accumulatedSteps.push({ type: 'text', content: currentTextStepContent })
    }

    // Update the message in real-time using steps structure
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
              // Update existing streaming message
              return {
                ...c,
                messages: c.messages.map((m: Message) => {
                  if (m.timestamp !== acc.streamingMessageTimestamp) return m

                  // Build steps: reasoning -> text -> tools -> text -> tools -> ...
                  const steps = m.steps || []
                  const lastStep = steps[steps.length - 1]

                  // If there was reasoning and now content is coming, finalize the reasoning step
                  if (lastStep?.type === 'reasoning') {
                    // Track this reasoning content so next reasoning step only shows new content
                    acc.previousReasoningContent = acc.accumulatedReasoning
                    return {
                      ...m,
                      content: acc.accumulatedContent,
                      steps: [
                        ...steps.slice(0, -1),
                        { type: 'reasoning' as const, content: lastStep.content, isStreaming: false },
                        { type: 'text' as const, content: currentTextStepContent }
                      ],
                      reasoning_content: acc.accumulatedReasoning || m.reasoning_content,
                      is_reasoning: false
                    }
                  }
                  // If last step is text, update it; otherwise create new text step
                  else if (lastStep?.type === 'text') {
                    return {
                      ...m,
                      content: acc.accumulatedContent,
                      steps: [
                        ...steps.slice(0, -1),
                        { type: 'text' as const, content: currentTextStepContent }
                      ],
                      reasoning_content: acc.accumulatedReasoning || m.reasoning_content,
                      is_reasoning: false
                    }
                  } else {
                    // Creating new text step after tool_executions (text only for this step)
                    return {
                      ...m,
                      content: acc.accumulatedContent,
                      steps: [
                        ...steps,
                        { type: 'text' as const, content: currentTextStepContent }
                      ],
                      reasoning_content: acc.accumulatedReasoning || m.reasoning_content,
                      is_reasoning: false
                    }
                  }
                })
              }
            } else {
              // Create new streaming message and set isLoading to false (streaming has started)
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
    acc.accumulatedReasoning += content

    // Update the message with accumulated reasoning in real-time using steps structure
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
              // Update existing message with reasoning step
              return {
                ...c,
                messages: c.messages.map((m: Message) => {
                  if (m.timestamp !== acc.streamingMessageTimestamp) return m

                  // Build steps: if last step is reasoning, update it; otherwise create new reasoning step
                  const steps = m.steps || []
                  const lastStep = steps[steps.length - 1]

                  if (lastStep?.type === 'reasoning') {
                    // Update existing reasoning step - extract delta from previous content
                    const reasoningDelta = getReasoningDelta(acc.accumulatedReasoning, acc.previousReasoningContent)
                    return {
                      ...m,
                      content: acc.accumulatedReasoning,
                      reasoning_content: acc.accumulatedReasoning,
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
                    const existingReasoningIdx = steps.findIndex((s) => s.type === 'reasoning')
                    const hasToolsBetween = existingReasoningIdx >= 0 &&
                      steps.slice(existingReasoningIdx + 1).some((s) => s.type === 'tool_executions')

                    if (existingReasoningIdx >= 0 && !hasToolsBetween) {
                      // Merge: update the existing reasoning step with full accumulated content
                      const reasoningDelta = getReasoningDelta(acc.accumulatedReasoning, acc.previousReasoningContent)
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
                        content: acc.accumulatedReasoning,
                        reasoning_content: acc.accumulatedReasoning,
                        is_reasoning: true,
                        steps: updatedSteps
                      }
                    }

                    // Tool calls occurred between reasoning blocks — create a new reasoning step
                    const reasoningDelta = getReasoningDelta(acc.accumulatedReasoning, acc.previousReasoningContent)
                    return {
                      ...m,
                      content: acc.accumulatedReasoning,
                      reasoning_content: acc.accumulatedReasoning,
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
                content: acc.accumulatedReasoning,
                timestamp: acc.streamingMessageTimestamp,
                model: model.name,
                model_id: model.model_id,
                provider: model.provider,
                provider_icon_slug: model.provider_icon_slug,
                provider_icon_url: model.provider_icon_url,
                model_icon_slug: model.model_icon_slug,
                model_icon_url: model.model_icon_url,
                is_reasoning: true,
                reasoning_content: acc.accumulatedReasoning,
                steps: [{ type: 'reasoning' as const, content: acc.accumulatedReasoning, isStreaming: true }],
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

  onWebSources: (sources: WebSource[]) => {
    // Accumulate web search sources
    acc.accumulatedWebSources = sources

    // Update the message with web search sources
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
              // Update existing streaming message with web sources
              return {
                ...c,
                messages: c.messages.map((m: Message) =>
                  m.timestamp === acc.streamingMessageTimestamp
                    ? {
                        ...m,
                        web_sources: acc.accumulatedWebSources
                      }
                    : m
                )
              }
            } else {
              // Create new streaming message with web sources
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
                web_sources: acc.accumulatedWebSources,
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
    if (imageData && !acc.accumulatedImages.includes(imageData)) {
      acc.accumulatedImages.push(imageData)
      

      // Update the message with accumulated images
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
                // Update existing streaming message with images
                return {
                  ...c,
                  messages: c.messages.map((m: Message) =>
                    m.timestamp === acc.streamingMessageTimestamp
                      ? {
                          ...m,
                          images: [...acc.accumulatedImages]
                        }
                      : m
                  )
                }
              } else {
                // Create new streaming message with images
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
                  images: [...acc.accumulatedImages],
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
  }
}
