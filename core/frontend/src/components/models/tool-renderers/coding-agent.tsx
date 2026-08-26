/**
 * coding_agent / plan_implementation / implement_plan / edit_plan: renders
 * only the premium CodingAgentDisplay card, replacing the standard row
 * entirely (no ToolFrame).
 */
import { CodingAgentDisplay } from '../CodingAgentDisplay'
import type { ToolRenderContext } from './types'

export function CodingAgentStandalone({
  execution,
  variant,
  chatId,
  pendingCodingAgentQuestion,
  onAnswerCodingAgentQuestion,
}: ToolRenderContext) {
  let codingResult: any = undefined
  let codingSteps: any[] = []

  if (execution.coding_agent_result) {
    codingResult = execution.coding_agent_result
  } else if (execution.result) {
    try {
      const parsed = typeof execution.result === 'string'
        ? JSON.parse(execution.result)
        : execution.result

      // Handle potential nested result wrapper from LangChain agent
      // Structure might be: { result: { success, data: { ... } } }
      // Or: { success, data: { ... } }
      const unwrapped = parsed.result || parsed
      const data = unwrapped.data || unwrapped

      codingResult = {
        job_id: data.job_id || unwrapped.job_id || parsed.job_id,
        success: unwrapped.success ?? data.success ?? parsed.success,
        summary: data.summary || unwrapped.summary || parsed.summary,
        files_created: data.files_created || unwrapped.files_created || parsed.files_created || [],
        files_modified: data.files_modified || unwrapped.files_modified || parsed.files_modified || [],
        error: unwrapped.error || data.error || parsed.error,
        duration_ms: data.duration_ms || unwrapped.duration_ms || parsed.duration_ms || 0,
        total_tokens: data.total_tokens || unwrapped.total_tokens || parsed.total_tokens,
      }
      codingSteps = data.steps || unwrapped.steps || parsed.steps || []
    } catch {
      // Parsing failed
    }
  }

  const steps = execution.coding_agent_steps && execution.coding_agent_steps.length > 0
    ? execution.coding_agent_steps
    : codingSteps

  const agentStatus = execution.isExecuting
    ? 'running'
    : codingResult?.success
      ? 'completed'
      : codingResult?.success === false
        ? 'failed'
        : 'pending'

  return (
    <div className="min-w-0 overflow-hidden">
      <CodingAgentDisplay
        task={(() => {
          try {
            const args = JSON.parse(execution.tool_call.function.arguments)
            return args.task || 'Coding task'
          } catch {
            return 'Coding task'
          }
        })()}
        jobId={codingResult?.job_id}
        status={agentStatus}
        steps={steps}
        result={codingResult}
        variant={variant}
        chatId={chatId}
        pendingQuestion={agentStatus === 'running' ? pendingCodingAgentQuestion : null}
        onAnswerQuestion={chatId && onAnswerCodingAgentQuestion ? (answer: string) => onAnswerCodingAgentQuestion(chatId, answer) : undefined}
      />
    </div>
  )
}
