/**
 * FileToolExecutionsDisplay Component
 *
 * Displays file tool executions with visual feedback like Claude.ai: an
 * icon, success/error state, arguments, and results. A thin dispatcher —
 * for each execution it looks the tool id up in the renderer registry
 * (`tool-renderers/registry.ts`) and hands off; the registry and its
 * renderer modules own everything tool-specific.
 */
import { getToolInfo, getFilePath } from './tool-renderers/tool-metadata'
import { getRendererEntry } from './tool-renderers/registry'
import { ToolFrame } from './tool-renderers/frame'
import type { FileToolExecution, ToolRenderContext } from './tool-renderers/types'
import type { CodingAgentQuestion } from '@/api/llm'

interface FileToolExecutionsDisplayProps {
  executions: FileToolExecution[]
  showBraveSearchMedia?: boolean  // Whether to show Brave Search media carousel (default: true for legacy, false when called from MessageSteps)
  variant?: 'chat' | 'code'  // 'code' uses dots instead of check/x, 'chat' is default
  onOpenIDE?: () => void  // Callback to open IDE for Coding Agent
  chatId?: string  // Chat ID for real-time progress tracking
  pendingCodingAgentQuestion?: CodingAgentQuestion | null
  onAnswerCodingAgentQuestion?: (chatId: string, answer: string) => void
}

export function FileToolExecutionsDisplay({
  executions,
  showBraveSearchMedia = true,
  variant = 'chat',
  onOpenIDE,
  chatId,
  pendingCodingAgentQuestion,
  onAnswerCodingAgentQuestion,
}: FileToolExecutionsDisplayProps) {
  const isCodeVariant = variant === 'code'

  if (!executions || executions.length === 0) {
    return null
  }

  return (
    <div className="space-y-1.5 mt-2">
      {executions.map((execution, index) => {
        const toolName = execution.tool_call.function.name
        const { icon: Icon, displayName } = getToolInfo(toolName, execution.tool_call.display_name)
        const filePath = getFilePath(toolName, execution.tool_call.function.arguments)
        const entry = getRendererEntry(toolName)

        const effectiveSuccess = entry.kind === 'framed' && entry.deriveEffectiveSuccess
          ? entry.deriveEffectiveSuccess(execution)
          : execution.success

        const context: ToolRenderContext = {
          execution,
          toolName,
          displayName,
          Icon,
          filePath,
          variant,
          isCodeVariant,
          effectiveSuccess,
          showBraveSearchMedia,
          chatId,
          pendingCodingAgentQuestion,
          onAnswerCodingAgentQuestion,
        }

        const key = execution.tool_call.id || index

        if (entry.kind === 'standalone') {
          const Standalone = entry.Component
          return <Standalone key={key} {...context} />
        }

        const { Header, Body, suppressErrorRow } = entry
        return (
          <ToolFrame
            key={key}
            context={context}
            header={<Header {...context} />}
            body={Body ? <Body {...context} /> : undefined}
            suppressErrorRow={suppressErrorRow}
          />
        )
      })}
    </div>
  )
}
