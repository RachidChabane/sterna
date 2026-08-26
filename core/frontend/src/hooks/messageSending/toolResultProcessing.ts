import type { CodingAgentResult, CodingAgentStep } from '@/api/llm'
import type { Spark } from '@/api/sparks'
import { CODING_AGENT_TOOLS } from './constants'
import type { ToolCallRequest } from './types'
import type { ToolResult, ToolExecution } from '@/components/models/types'

/** A spark as returned nested inside a create_spark/update_spark tool result. */
export type SparkFromToolResult = Pick<Spark, 'id' | 'title' | 'framework' | 'code' | 'version' | 'assets' | 'download_url'>

/** Shape of a create_spark/update_spark tool's raw JSON result: `{status, spark}`. */
interface SparkToolResultData {
  status?: string
  spark?: SparkFromToolResult
}

/**
 * Pull newly-created/updated sparks out of `create_spark`/`update_spark` tool
 * results. Sparks returned here are already persisted by the backend — callers
 * must not re-persist them.
 */
export function extractSparksFromToolResults(toolCalls: ToolCallRequest[], results: ToolResult[]): SparkFromToolResult[] {
  const sparks: SparkFromToolResult[] = []
  toolCalls.forEach((tc, idx) => {
    const toolName = tc.function?.name
    if (toolName === 'create_spark' || toolName === 'update_spark') {
      // Backend sends: {tool_call, result: {status, spark}, success}
      const toolResult = results[idx]?.result as SparkToolResultData | undefined
      if (toolResult?.status === 'success' && toolResult.spark) {
        sparks.push({
          id: toolResult.spark.id,
          title: toolResult.spark.title,
          framework: toolResult.spark.framework,
          code: toolResult.spark.code, // Code included in tool response
          version: toolResult.spark.version,
          assets: toolResult.spark.assets, // Assets available via window.__SPARK_ASSETS__
          download_url: toolResult.spark.download_url, // For pdf/docx/csv/ics types
        })
      }
    }
  })
  return sparks
}

/**
 * Build the `file_tool_executions` display array for a completed tool-call batch.
 * Coding Agent tools (see CODING_AGENT_TOOLS) get their steps/result attached from
 * the tool result's `coding_agent_data`, falling back to the in-flight accumulated
 * Coding Agent state when the backend hasn't sent a fuller payload yet.
 */
/** Shape of a coding-agent tool's raw JSON result: `{success, summary, files_*, coding_agent_data}`. */
interface CodingAgentToolResultData {
  success?: boolean
  summary?: string
  files_created?: string[]
  files_modified?: string[]
  coding_agent_data?: CodingAgentResult
}

export function buildExecutionsFromToolResults(
  toolCalls: ToolCallRequest[],
  results: ToolResult[],
  accumulatedCodingAgentSteps: CodingAgentStep[],
  accumulatedCodingAgentResult: CodingAgentResult | null,
): ToolExecution[] {
  return toolCalls.map((tc, idx) => {
    const result = results[idx] as CodingAgentToolResultData | null
    const baseExec = {
      tool_call: tc,
      result: result as ToolResult,
      success: result?.success !== false, // Consider success if not explicitly false
      isExecuting: false, // Explicitly mark as completed
    }

    // For coding_agent, include the steps and result from coding_agent_data
    if (CODING_AGENT_TOOLS.has(tc.function?.name)) {
      // Backend sends coding_agent_data with full execution details
      const codingData = result?.coding_agent_data
      const steps = codingData?.steps || accumulatedCodingAgentSteps || []
      return {
        ...baseExec,
        coding_agent_steps: [...steps],
        // Neither a fuller coding_agent_data payload nor an accumulated result is
        // available yet — build the partial shape the renderer already tolerates
        // (job_id/duration_ms are absent here, same as before this was typed).
        coding_agent_result: codingData || accumulatedCodingAgentResult || {
          success: result?.success ?? false,
          summary: result?.summary,
          files_created: result?.files_created || [],
          files_modified: result?.files_modified || [],
        } as CodingAgentResult,
      }
    }
    return baseExec
  })
}
