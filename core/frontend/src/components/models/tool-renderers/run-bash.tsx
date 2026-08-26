/**
 * run_bash: the `$ command` line with a collapsible output section, all
 * inside the row itself (unlike every other tool, its result never
 * appears as a frame body). Also exports the error-pattern detection the
 * dispatcher uses to recompute `effectiveSuccess` for this one tool id,
 * and to suppress the frame's own error row in favor of this one.
 */
import { memo, useState } from 'react'
import { cn } from '@/lib/utils'
import { ChevronRight } from 'lucide-react'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { tryParseJSON, sanitizeOutput } from './shared'
import type { ToolRenderContext, FileToolExecution } from './types'

// Helper to extract output from a string that looks like JSON but may be malformed
// Tries to find "output": "..." pattern and extract the value
const extractOutputFromString = (str: string): string | null => {
  // Try to find "output": "..." pattern
  const outputMatch = str.match(/"output"\s*:\s*"/)
  if (!outputMatch) return null

  const startIdx = outputMatch.index! + outputMatch[0].length
  let result = ''
  let i = startIdx
  let escaped = false

  // Parse the string value, handling escapes
  while (i < str.length) {
    const char = str[i]
    if (escaped) {
      // Handle escape sequences
      if (char === 'n') result += '\n'
      else if (char === 't') result += '\t'
      else if (char === 'r') result += '\r'
      else if (char === '\\') result += '\\'
      else if (char === '"') result += '"'
      else result += char
      escaped = false
    } else if (char === '\\') {
      escaped = true
    } else if (char === '"') {
      // End of string
      break
    } else {
      result += char
    }
    i++
  }

  return result
}

// Helper to extract bash output from various result formats
const extractBashOutput = (result: any): { output: string, error: string, exitCode?: number } => {
  // Handle null/undefined
  if (!result) return { output: '', error: '' }

  // If result is a string, first try to extract output directly using regex
  // This handles cases where JSON.parse fails due to malformed data
  if (typeof result === 'string' && result.includes('"output"')) {
    const extractedOutput = extractOutputFromString(result)
    if (extractedOutput) {
      return { output: extractedOutput, error: '' }
    }
  }

  // Parse if string
  let data = tryParseJSON(result)

  // Handle double-encoded JSON
  data = tryParseJSON(data)

  // Navigate through possible nested structures
  // Structure might be: { result: { data: { output } } } or { data: { output } } or { output }
  if (data?.result) {
    data = tryParseJSON(data.result)
  }
  if (data?.data) {
    data = tryParseJSON(data.data)
  }

  // Now data should be { output, error, exit_code } or just a string
  if (typeof data === 'string') {
    // If it still looks like JSON with output field, try to extract
    if (data.includes('"output"')) {
      const extractedOutput = extractOutputFromString(data)
      if (extractedOutput) {
        return { output: extractedOutput, error: '' }
      }
    }
    return { output: data, error: '' }
  }

  if (typeof data === 'object' && data !== null) {
    const output = typeof data.output === 'string' ? data.output : ''
    const error = typeof data.error === 'string' ? data.error : ''
    const exitCode = typeof data.exit_code === 'number' ? data.exit_code : undefined
    return { output, error, exitCode }
  }

  return { output: '', error: '' }
}

// Common error patterns in bash output that indicate failure even if exit_code is 0 or success is true
const BASH_ERROR_PATTERNS = [
  /command not found/i,
  /no such file or directory/i,
  /permission denied/i,
  /cannot find/i,
  /error:/i,
  /fatal:/i,
  /failed:/i,
  /exception/i,
  /traceback/i,
]

// Check if output contains error patterns
const hasErrorPatterns = (text: string): boolean => {
  return BASH_ERROR_PATTERNS.some(pattern => pattern.test(text))
}

// For run_bash, output can contain error patterns even when success is true
// (or reported as null while executing) — treat that as a failure.
export function deriveRunBashEffectiveSuccess(execution: FileToolExecution): boolean | null | undefined {
  let effectiveSuccess = execution.success
  if (execution.result && !execution.isExecuting) {
    const { output, error } = extractBashOutput(execution.result)
    const displayContent = output || error
    if (displayContent && hasErrorPatterns(displayContent)) {
      effectiveSuccess = false
    }
  }
  return effectiveSuccess
}

export function RunBashHeader({ execution, variant, effectiveSuccess }: ToolRenderContext) {
  const command = (() => {
    try {
      const args = JSON.parse(execution.tool_call.function.arguments)
      return args.command || ''
    } catch {
      return ''
    }
  })()

  return (
    <RunBashDisplay
      command={command}
      result={execution.result}
      success={effectiveSuccess}
      isExecuting={execution.isExecuting}
      variant={variant}
    />
  )
}

// Component for displaying run_bash with command inline and collapsible output
const RunBashDisplay = memo(({
  command,
  result,
  success,
  isExecuting,
  variant = 'chat'
}: {
  command: string
  result: any
  success?: boolean | null
  isExecuting?: boolean
  variant?: 'chat' | 'code'
}) => {
  const isCodeVariant = variant === 'code'
  const [isExpanded, setIsExpanded] = useState(false)

  const { output, error } = extractBashOutput(result)
  const displayContent = output || error
  const hasOutput = !!displayContent && !isExecuting
  const isError = success === false || (displayContent && hasErrorPatterns(displayContent))

  // Truncate command for display
  const displayCommand = command.length > 80 ? command.slice(0, 80) + '...' : command

  return (
    <Collapsible open={isExpanded} onOpenChange={setIsExpanded} className="flex-1 min-w-0">
      <div className="flex items-center gap-1.5 min-w-0">
        <span className={cn(
          isCodeVariant ? "text-xs" : "text-sm"
        )}>
          <span className="font-medium text-foreground/70">Bash</span>
          {' '}
          <code className="font-mono text-muted-foreground bg-muted/50 px-1 py-0.5 rounded">{displayCommand}</code>
        </span>
        {hasOutput && (
          <CollapsibleTrigger
            onClick={(e) => e.stopPropagation()}
            className="flex items-center gap-1 text-muted-foreground hover:text-foreground transition-colors shrink-0"
          >
            <ChevronRight className={cn(
              "h-3 w-3 transition-transform duration-200",
              isExpanded && "rotate-90"
            )} />
          </CollapsibleTrigger>
        )}
      </div>
      {displayContent && (
        <CollapsibleContent>
          <div className="mt-1 flex">
            <span className="text-muted-foreground/60 mr-1 text-xs">⎿</span>
            <pre className={cn(
              "text-xs font-mono whitespace-pre-wrap max-h-[300px] overflow-y-auto",
              isError ? "text-red-400" : "text-muted-foreground"
            )}>
              {sanitizeOutput(displayContent)}
            </pre>
          </div>
        </CollapsibleContent>
      )}
    </Collapsible>
  )
})
