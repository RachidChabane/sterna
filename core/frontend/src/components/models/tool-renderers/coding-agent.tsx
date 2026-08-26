/**
 * coding_agent / plan_implementation / implement_plan / edit_plan: renders
 * only the premium CodingAgentDisplay card, replacing the standard row
 * entirely (no ToolFrame).
 */
import { CodingAgentDisplay } from '../CodingAgentDisplay'
import { isRecord, asString, asNumber, asStringArray } from './shared'
import type { ToolRenderContext } from './types'
import type { CodingAgentResult, CodingAgentStep } from '@/api/llm'

export function CodingAgentStandalone({
  execution,
  variant,
  chatId,
  pendingCodingAgentQuestion,
  onAnswerCodingAgentQuestion,
}: ToolRenderContext) {
  let codingResult: CodingAgentResult | undefined = undefined
  let codingSteps: CodingAgentStep[] = []
  // Tri-state: `undefined` means the parsed blob didn't carry a recognizable
  // success flag at all (distinct from an explicit `false`) — drives the
  // 'pending' vs 'failed' distinction in agentStatus below.
  let parsedSuccess: boolean | undefined = undefined

  if (execution.coding_agent_result) {
    codingResult = execution.coding_agent_result
    parsedSuccess = execution.coding_agent_result.success
  } else if (execution.result) {
    try {
      const raw: unknown = typeof execution.result === 'string'
        ? JSON.parse(execution.result)
        : execution.result

      // Handle potential nested result wrapper from LangChain agent
      // Structure might be: { result: { success, data: { ... } } }
      // Or: { success, data: { ... } }
      const parsed = isRecord(raw) ? raw : {}
      const unwrapped = isRecord(parsed.result) ? parsed.result : parsed
      const data = isRecord(unwrapped.data) ? unwrapped.data : unwrapped

      const successValue = unwrapped.success ?? data.success ?? parsed.success
      parsedSuccess = typeof successValue === 'boolean' ? successValue : undefined

      codingResult = {
        job_id: asString(data.job_id ?? unwrapped.job_id ?? parsed.job_id) || '',
        success: parsedSuccess ?? false,
        summary: asString(data.summary ?? unwrapped.summary ?? parsed.summary),
        files_created: asStringArray(data.files_created ?? unwrapped.files_created ?? parsed.files_created) || [],
        files_modified: asStringArray(data.files_modified ?? unwrapped.files_modified ?? parsed.files_modified) || [],
        error: asString(unwrapped.error ?? data.error ?? parsed.error),
        duration_ms: asNumber(data.duration_ms ?? unwrapped.duration_ms ?? parsed.duration_ms) || 0,
        total_tokens: asNumber(data.total_tokens ?? unwrapped.total_tokens ?? parsed.total_tokens),
      }
      // Steps come from a loosely-shaped LangChain agent blob (like `result`
      // above): pass them through as-is rather than dropping entries that
      // don't carry every canonical field, matching how CodingAgentDisplay
      // itself treats this same data (see its `as ExtendedStep[]` cast).
      const rawSteps = data.steps ?? unwrapped.steps ?? parsed.steps
      codingSteps = Array.isArray(rawSteps) ? (rawSteps as CodingAgentStep[]) : []
    } catch {
      // Parsing failed
      parsedSuccess = undefined
    }
  }

  const steps = execution.coding_agent_steps && execution.coding_agent_steps.length > 0
    ? execution.coding_agent_steps
    : codingSteps

  const agentStatus = execution.isExecuting
    ? 'running'
    : parsedSuccess
      ? 'completed'
      : parsedSuccess === false
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
