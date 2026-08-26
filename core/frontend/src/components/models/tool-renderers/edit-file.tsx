/**
 * edit_file body: an inline unified-diff view, matching the Coding Agent's
 * diff style.
 */
import { memo, useState } from 'react'
import { cn } from '@/lib/utils'
import { useTheme } from '@/hooks/useTheme'
import { ChevronRight } from 'lucide-react'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { parseDiffLines, deepParse, isRecord, asString } from './shared'
import type { ToolRenderContext } from './types'
import type { ToolResult } from '@/api/llm'

const MAX_VISIBLE_LINES = 15

export function EditFileBody({ execution, filePath }: ToolRenderContext) {
  if (!execution.result || execution.isExecuting) return null

  const args: { path?: string; old_content?: string; new_content?: string } = (() => {
    try { return JSON.parse(execution.tool_call.function.arguments) } catch { return {} }
  })()

  return <EditFileDiffResult result={execution.result} filePath={filePath || undefined} args={args} />
}

const EditFileDiffResult = memo(({ result, filePath, args }: {
  result: ToolResult
  filePath?: string
  args?: { path?: string; old_content?: string; new_content?: string }
}) => {
  const [showFullDiff, setShowFullDiff] = useState(false)
  const { isDark } = useTheme()

  // Extract diff - could be in various places
  const diffOf = (v: unknown): string | undefined => (isRecord(v) ? asString(v.diff) : undefined)
  const dataOf = (v: unknown): unknown => (isRecord(v) ? v.data : undefined)

  const parsedResult = deepParse(result)
  const actualResult = (isRecord(parsedResult) ? parsedResult.result : undefined) || parsedResult

  let diff = diffOf(actualResult) || diffOf(dataOf(actualResult)) || diffOf(dataOf(parsedResult)) || diffOf(parsedResult)

  // If no diff from result, generate one from args
  if (!diff && args?.old_content && args?.new_content) {
    // Generate a simple diff representation
    const oldLines = args.old_content.split('\n')
    const newLines = args.new_content.split('\n')
    const diffParts: string[] = []
    diffParts.push(`--- a/${args.path || filePath || 'file'}`)
    diffParts.push(`+++ b/${args.path || filePath || 'file'}`)
    diffParts.push(`@@ -1,${oldLines.length} +1,${newLines.length} @@`)
    oldLines.forEach(line => diffParts.push(`-${line}`))
    newLines.forEach(line => diffParts.push(`+${line}`))
    diff = diffParts.join('\n')
  }

  if (!diff) return null

  const diffLines = parseDiffLines(diff)
  const addedCount = diffLines.filter(l => l.type === 'added').length
  const removedCount = diffLines.filter(l => l.type === 'removed').length
  const visibleLines = showFullDiff ? diffLines : diffLines.slice(0, MAX_VISIBLE_LINES)

  return (
    <Collapsible open={showFullDiff} onOpenChange={setShowFullDiff} className="ml-5">
      {/* Header - matches WriteFileContentResult style */}
      <CollapsibleTrigger className="flex items-center gap-1.5 text-xs text-muted-foreground/60 hover:text-muted-foreground transition-colors">
        <ChevronRight className={cn(
          "h-3 w-3 transition-transform duration-200",
          showFullDiff && "rotate-90"
        )} />
        <span className="text-amber-500">
          {addedCount > 0 && `+${addedCount}`}
          {addedCount > 0 && removedCount > 0 && ' / '}
          {removedCount > 0 && <span className="text-red-400">-{removedCount}</span>}
          {addedCount === 0 && removedCount === 0 && 'No changes'}
        </span>
        <span className="text-muted-foreground/40">·</span>
        <span>{showFullDiff ? 'Hide diff' : 'View diff'}</span>
      </CollapsibleTrigger>

      <CollapsibleContent>
        <div className={cn(
          "mt-1.5 pl-3 border-l border-border/40 overflow-hidden rounded-r",
          isDark ? "bg-card/30" : "bg-slate-50/50"
        )}>
          {/* Diff lines */}
          <div className="text-[10px] font-mono leading-[1.5] max-h-[250px] overflow-y-auto">
        {visibleLines.map((line, index) => {
          // Theme-aware styles based on line type - high contrast for light mode
          let bgClass = ''
          let textClass = isDark ? 'text-muted-foreground' : 'text-foreground/80'

          switch (line.type) {
            case 'header':
              bgClass = isDark ? 'bg-muted/30' : 'bg-slate-100'
              textClass = isDark ? 'text-muted-foreground/70' : 'text-slate-500'
              break
            case 'hunk':
              bgClass = isDark ? 'bg-blue-500/10' : 'bg-blue-50'
              textClass = isDark ? 'text-blue-400' : 'text-blue-700 font-medium'
              break
            case 'removed':
              bgClass = isDark ? 'bg-red-500/15' : 'bg-red-50'
              textClass = isDark ? 'text-red-400' : 'text-red-700'
              break
            case 'added':
              bgClass = isDark ? 'bg-emerald-500/15' : 'bg-emerald-50'
              textClass = isDark ? 'text-emerald-400' : 'text-emerald-700'
              break
            case 'context':
              textClass = isDark ? 'text-muted-foreground/80' : 'text-slate-600'
              break
          }

          const showLineNums = line.type !== 'header' && line.type !== 'hunk'

          return (
            <div
              key={index}
              className={cn("flex", bgClass)}
            >
              {/* Line numbers */}
              {showLineNums && (
                <div className={cn(
                  "flex-shrink-0 w-16 flex select-none border-r",
                  isDark ? "text-muted-foreground/40 border-border/30" : "text-slate-400 border-slate-200"
                )}>
                  <span className="w-8 text-right pr-1">
                    {line.type === 'added' ? '' : line.oldLineNum || ''}
                  </span>
                  <span className="w-8 text-right pr-1">
                    {line.type === 'removed' ? '' : line.newLineNum || ''}
                  </span>
                </div>
              )}
              {!showLineNums && (
                <div className={cn(
                  "flex-shrink-0 w-16 border-r",
                  isDark ? "border-border/30" : "border-slate-200"
                )} />
              )}

              {/* Content */}
              <pre className={cn("flex-1 px-2 whitespace-pre-wrap break-all", textClass)}>
                {line.type === 'header' || line.type === 'hunk'
                  ? line.content
                  : line.content.slice(1) || ' '}
              </pre>
            </div>
          )
        })}
          </div>
        </div>
      </CollapsibleContent>
    </Collapsible>
  )
})
