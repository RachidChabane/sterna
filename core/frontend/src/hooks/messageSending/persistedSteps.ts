/**
 * Build the `steps` array persisted to the backend for an assistant message:
 * an optional leading reasoning step, then the tracked text/tool_executions
 * steps in their original interleaved order (text -> tool_executions -> text -> ...),
 * so the reload view matches what was shown during streaming.
 *
 * On the abort path a tool call may still be mid-flight when persistence runs, so
 * `filterIncomplete` drops executions that have neither finished nor produced a
 * result yet, and skips an entire tool_executions step if nothing in it qualifies.
 * The success/onDone path has no such gap — every execution is already resolved —
 * so it persists them all unfiltered.
 */
export function buildPersistedSteps(
  accumulatedReasoning: string,
  accumulatedSteps: any[],
  options: { filterIncomplete: boolean },
): any[] {
  const persistedSteps: any[] = []

  if (accumulatedReasoning) {
    persistedSteps.push({ type: 'reasoning', content: accumulatedReasoning, isStreaming: false })
  }

  for (const step of accumulatedSteps) {
    if (step.type === 'text' && step.content?.trim()) {
      persistedSteps.push({ type: 'text', content: step.content })
      continue
    }
    if (step.type !== 'tool_executions') continue

    const decorate = (exec: any) => ({
      ...exec,
      isExecuting: false,
      // Ensure coding agent data persists
      ...(exec.coding_agent_steps && { coding_agent_steps: exec.coding_agent_steps }),
      ...(exec.coding_agent_result && { coding_agent_result: exec.coding_agent_result }),
    })

    if (options.filterIncomplete) {
      const completedExecs = step.executions
        ?.filter((exec: any) => !exec.isExecuting || exec.result)
        .map(decorate)
      if (completedExecs?.length > 0) {
        persistedSteps.push({ type: 'tool_executions', executions: completedExecs, isExecuting: false })
      }
    } else {
      persistedSteps.push({
        type: 'tool_executions',
        executions: step.executions?.map(decorate),
        isExecuting: false,
      })
    }
  }

  return persistedSteps
}
