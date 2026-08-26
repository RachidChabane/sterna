/**
 * Shared types for the per-tool renderer registry.
 *
 * A `RendererEntry` is what `registry.ts` maps a tool id to. Most tools
 * render inside the shared frame (`ToolFrame`): the entry supplies a
 * `Header` component for the row's content slot and, optionally, a `Body`
 * component for the section that follows the row. A tool whose result
 * replaces the row entirely (Coding Agent) uses a `standalone` entry and
 * bypasses the frame.
 */
import type { ComponentType } from 'react'
import type { CodingAgentStep, CodingAgentResult, CodingAgentQuestion } from '@/api/llm'

export interface FileToolExecution {
  tool_call: {
    id: string
    type: 'function'
    function: {
      name: string
      arguments: string
    }
    display_name?: string  // User-friendly display name (from backend)
    server_icon_url?: string  // MCP server icon URL (from backend)
    server_icon_invert?: boolean  // Whether to invert icon in dark mode
  }
  result: any
  success: boolean | null
  isExecuting?: boolean  // True while tool is executing
  // Coding Agent specific fields
  coding_agent_steps?: CodingAgentStep[]  // Streamed execution steps
  coding_agent_result?: CodingAgentResult  // Final execution result
}

/** Values every renderer needs, derived once by the dispatcher. */
export interface ToolRenderContext {
  execution: FileToolExecution
  toolName: string
  displayName: string
  Icon: ComponentType<{ className?: string }>
  filePath: string | null
  variant: 'chat' | 'code'
  isCodeVariant: boolean
  /** `execution.success`, except run_bash recomputes it from output error patterns. */
  effectiveSuccess: boolean | null | undefined
  showBraveSearchMedia: boolean
  chatId?: string
  pendingCodingAgentQuestion?: CodingAgentQuestion | null
  onAnswerCodingAgentQuestion?: (chatId: string, answer: string) => void
}

type ToolHeaderComponent = ComponentType<ToolRenderContext>
type ToolBodyComponent = ComponentType<ToolRenderContext>
type ToolStandaloneComponent = ComponentType<ToolRenderContext>

/** A tool rendered inside the shared frame (row + optional error indicator). */
export interface FramedRendererEntry {
  kind: 'framed'
  Header: ToolHeaderComponent
  Body?: ToolBodyComponent
  /** run_bash renders its own error state inline and suppresses the frame's row. */
  suppressErrorRow?: boolean
  /**
   * Recompute `effectiveSuccess` from the execution (run_bash treats
   * certain error patterns in its output as a failure even when
   * `execution.success` is true). Omitted for every other tool, where
   * `effectiveSuccess` is just `execution.success`.
   */
  deriveEffectiveSuccess?: (execution: FileToolExecution) => boolean | null | undefined
}

/** A tool that replaces the row entirely (Coding Agent). */
interface StandaloneRendererEntry {
  kind: 'standalone'
  Component: ToolStandaloneComponent
}

export type RendererEntry = FramedRendererEntry | StandaloneRendererEntry
