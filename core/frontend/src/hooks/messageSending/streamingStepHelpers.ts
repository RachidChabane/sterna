import type { Message } from '@/components/models/types'

type MessageSteps = NonNullable<Message['steps']>

/**
 * Extract only the new portion of reasoning content — handles both delta-style and
 * full-accumulated-content reasoning APIs. When `current` starts with `previous` it
 * is treated as accumulated content and the delta is sliced off; otherwise the model
 * sent fresh content and the full string is returned.
 */
export function getReasoningDelta(current: string, previous: string): string {
  if (!previous) return current
  if (current.startsWith(previous)) {
    return current.slice(previous.length)
  }
  return current
}

/**
 * Clear any stuck `isExecuting` flags and drop orphaned executing tool_executions
 * steps once a stream has finished — safety cleanup run right before the final
 * message state is committed. A step is dropped only when every one of its
 * executions already has a completed duplicate elsewhere in `steps`.
 */
export function cleanupStreamingSteps(steps: Message['steps']): MessageSteps {
  const list: MessageSteps = steps || []

  const completedToolCallIds = new Set<string>()
  for (const step of list) {
    if (step.type === 'tool_executions' && !step.isExecuting) {
      for (const exec of (step.executions || [])) {
        if (exec.tool_call?.id) {
          completedToolCallIds.add(exec.tool_call.id)
        }
      }
    }
  }

  return list
    .filter((step) => {
      if (step.type === 'tool_executions' && step.isExecuting) {
        const allHaveCompletedDuplicates = (step.executions || []).every(
          (exec) => exec.tool_call?.id && completedToolCallIds.has(exec.tool_call.id)
        )
        if (allHaveCompletedDuplicates && step.executions?.length > 0) {
          return false
        }
      }
      return true
    })
    .map((step) => {
      if (step.type === 'tool_executions' && step.isExecuting) {
        return {
          ...step,
          isExecuting: false,
          executions: step.executions?.map((exec) => ({
            ...exec,
            isExecuting: false
          }))
        }
      }
      return step
    })
}
