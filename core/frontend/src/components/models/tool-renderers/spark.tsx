/** update_spark body: a diff between the previous and new spark code. */
import { memo, useState } from 'react'
import { cn } from '@/lib/utils'
import { useTheme } from '@/hooks/useTheme'
import { Zap } from 'lucide-react'
import { parseDiffLines, deepParse, isRecord, asString, asNumber } from './shared'
import type { ToolRenderContext } from './types'
import type { ToolResult } from '@/api/llm'

const MAX_VISIBLE_LINES = 15

export function SparkUpdateBody({ execution, effectiveSuccess }: ToolRenderContext) {
  if (!execution.result || execution.isExecuting || effectiveSuccess === false) return null
  return <SparkUpdateDiff result={execution.result} />
}

// Component for displaying spark update diff
const SparkUpdateDiff = memo(({ result }: { result: ToolResult }) => {
  const [showFullDiff, setShowFullDiff] = useState(false)
  const { isDark } = useTheme()

  const parsedResult = deepParse(result)

  // Extract old and new code from spark result
  // Handle both direct spark and nested result.spark structures
  const nestedResult = isRecord(parsedResult) ? parsedResult.result : undefined
  const spark = (isRecord(parsedResult) ? parsedResult.spark : undefined) ?? (isRecord(nestedResult) ? nestedResult.spark : undefined)
  const oldCode = isRecord(spark) ? asString(spark.old_code) : undefined
  const newCode = isRecord(spark) ? asString(spark.code) : undefined
  const title = (isRecord(spark) ? asString(spark.title) : undefined) || 'Spark'
  const version = isRecord(spark) ? asNumber(spark.version) : undefined

  if (!oldCode || !newCode) return null

  // Generate diff from old and new code
  const oldLines = oldCode.split('\n')
  const newLines = newCode.split('\n')
  const diffParts: string[] = []
  diffParts.push(`--- a/${title} v${(version || 1) - 1}`)
  diffParts.push(`+++ b/${title} v${version || 1}`)
  diffParts.push(`@@ -1,${oldLines.length} +1,${newLines.length} @@`)
  oldLines.forEach((line: string) => diffParts.push(`-${line}`))
  newLines.forEach((line: string) => diffParts.push(`+${line}`))
  const diff = diffParts.join('\n')

  const diffLines = parseDiffLines(diff)
  const visibleLines = showFullDiff ? diffLines : diffLines.slice(0, MAX_VISIBLE_LINES)
  const hasMoreLines = diffLines.length > MAX_VISIBLE_LINES

  return (
    <div className={cn(
      "mt-1.5 ml-5 border rounded-md overflow-hidden",
      isDark ? "border-border/60 bg-card/50" : "border-border bg-white"
    )}>
      {/* Header */}
      <div className={cn(
        "px-2 py-1 text-xs flex items-center gap-2 border-b",
        isDark ? "bg-amber-500/10 border-border/30" : "bg-amber-50 border-amber-200"
      )}>
        <Zap className={cn("w-3 h-3", isDark ? "text-amber-400" : "text-amber-600")} />
        <span className={isDark ? "text-amber-400" : "text-amber-700"}>
          Code changes in {title}
        </span>
      </div>

      {/* Diff lines */}
      <div className="text-[11px] font-mono leading-[1.6] max-h-[300px] overflow-y-auto">
        {visibleLines.map((line, index) => {
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
            <div key={index} className={cn("flex", bgClass)}>
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
              <pre className={cn("flex-1 px-2 whitespace-pre-wrap break-all", textClass)}>
                {line.type === 'header' || line.type === 'hunk'
                  ? line.content
                  : line.content.slice(1) || ' '}
              </pre>
            </div>
          )
        })}
      </div>

      {/* Show more link */}
      {hasMoreLines && !showFullDiff && (
        <button
          onClick={() => setShowFullDiff(true)}
          className={cn(
            "w-full py-1.5 text-center text-xs transition-colors border-t",
            isDark
              ? "text-muted-foreground hover:text-foreground hover:bg-muted/30 border-border/30"
              : "text-slate-500 hover:text-slate-700 hover:bg-slate-50 border-slate-200"
          )}
        >
          Show full diff ({diffLines.length - MAX_VISIBLE_LINES} more lines)
        </button>
      )}
    </div>
  )
})
