import { llmApi } from '@/api/llm'
import type { StreamCallbacksContext } from './context'
import { buildMessageContentCallbacks } from './messageContentCallbacks'
import { buildToolExecutionCallbacks } from './toolExecutionCallbacks'
import { buildCodingAgentCallbacks } from './codingAgentCallbacks'
import { buildLifecycleCallbacks } from './lifecycleCallbacks'

export type { StreamCallbacksContext } from './context'

/** The callbacks object shape llmApi.completeStream expects, derived from its own signature. */
export type StreamCallbacks = Parameters<typeof llmApi.completeStream>[1]

/**
 * Assemble the full set of callbacks passed to llmApi.completeStream for one
 * sendToModel call, composed from the per-concern builders above.
 */
export function buildStreamCallbacks(ctx: StreamCallbacksContext): StreamCallbacks {
  return {
    ...buildMessageContentCallbacks(ctx),
    ...buildToolExecutionCallbacks(ctx),
    ...buildCodingAgentCallbacks(ctx),
    ...buildLifecycleCallbacks(ctx),
  }
}
