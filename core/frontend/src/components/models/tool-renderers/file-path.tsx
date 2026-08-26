/**
 * Header for the file-op tools (read/write/edit/delete/list/create-dir/
 * rename): tool name + path, inline. `filePath` comes from parsing the
 * call's arguments, not from the tool id, so a call with no resolvable
 * path (bad/missing args) falls through to the generic header exactly
 * like an unrecognized tool would.
 */
import { deepParse } from './shared'
import { GenericHeader } from './generic'
import type { ToolRenderContext } from './types'

// Extract line count from read_file result
const getReadLineCount = (result: any): number | null => {
  if (!result) return null
  try {
    let data = deepParse(result)

    // Navigate nested structures: result.result.data or result.data
    if (data?.result) data = deepParse(data.result)
    if (data?.data) data = deepParse(data.data)

    // Check for lines field from backend
    if (typeof data?.lines === 'number') return data.lines

    // Count lines in content as fallback
    const content = data?.content
    if (typeof content === 'string') {
      return content.split('\n').length
    }
    return null
  } catch {
    return null
  }
}

export function FilePathHeader(context: ToolRenderContext) {
  const { execution, toolName, displayName, filePath, isCodeVariant } = context

  if (!filePath) {
    return <GenericHeader {...context} />
  }

  return (
    <div>
      <div className="flex items-center gap-1.5">
        <span className={isCodeVariant ? "text-foreground/70 font-medium" : "text-foreground font-medium"}>{displayName}</span>
        <code className="font-mono text-muted-foreground bg-muted/50 px-1 py-0.5 rounded truncate">{filePath}</code>
      </div>
      {/* Read file: show line count */}
      {toolName === 'read_file' && execution.result && !execution.isExecuting && (() => {
        const lineCount = getReadLineCount(execution.result)
        return lineCount ? (
          <div className="text-xs text-muted-foreground/60 flex items-center">
            <span className="mr-1">⎿</span>Read {lineCount} line{lineCount !== 1 ? 's' : ''}
          </div>
        ) : null
      })()}
    </div>
  )
}
