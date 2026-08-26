import type { CodingAgentResult, CodingAgentStep } from '@/api/llm'

/** Usage/cost snapshot captured from the most recent onUsageUpdate stream event. */
interface StreamUsageSnapshot {
  usage: { prompt_tokens: number; completion_tokens: number; total_tokens: number }
  cost: number
  prompt_cost: number
  completion_cost: number
  generation_id?: string
  generation_ids?: string[]
}

/**
 * Mutable accumulator for a single sendToModel streaming call. The stream callbacks
 * (onContent, onReasoning, onFileToolExecuted, ...) mutate these fields in place as
 * chunks arrive; the fields are read back once the stream completes (or aborts) to
 * build the final UI message and the payload persisted to the backend.
 */
export interface StreamAccumulator {
  accumulatedContent: string
  /** Never reset (unlike accumulatedContent, which resets after each tool execution) — used for final persistence. */
  totalContentForPersistence: string
  accumulatedReasoning: string
  /** Content of previous reasoning steps, for delta calculation via getReasoningDelta. */
  previousReasoningContent: string
  accumulatedWebSources: any[]
  allToolExecutions: any[]
  accumulatedSparksFromTools: any[]
  /** Interleaved text / reasoning / tool_executions steps, tracked for persistence. */
  accumulatedSteps: any[]
  /** Index into accumulatedContent where the current text step's content starts. */
  currentTextStepStartIndex: number
  accumulatedImages: string[]
  accumulatedCodingAgentSteps: CodingAgentStep[]
  accumulatedCodingAgentResult: CodingAgentResult | null
  sternaRouteData: any
  streamingMessageTimestamp: Date
  messageMetadata: any
  lastUsageUpdate: StreamUsageSnapshot | null
  /** OpenRouter generation ID, used to query precise usage after an abort. */
  generationId: string | null
  /** All generation IDs across tool-loop iterations, for comprehensive abort billing. */
  generationIds: string[]
}

export function createStreamAccumulator(streamingMessageTimestamp: Date): StreamAccumulator {
  return {
    accumulatedContent: '',
    totalContentForPersistence: '',
    accumulatedReasoning: '',
    previousReasoningContent: '',
    accumulatedWebSources: [],
    allToolExecutions: [],
    accumulatedSparksFromTools: [],
    accumulatedSteps: [],
    currentTextStepStartIndex: 0,
    accumulatedImages: [],
    accumulatedCodingAgentSteps: [],
    accumulatedCodingAgentResult: null,
    sternaRouteData: null,
    streamingMessageTimestamp,
    messageMetadata: null,
    lastUsageUpdate: null,
    generationId: null,
    generationIds: [],
  }
}
