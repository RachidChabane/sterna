/** search_code body: the match list, grouped by file:line. */
import { memo, useState, useMemo } from 'react'
import { cn } from '@/lib/utils'
import { useTheme } from '@/hooks/useTheme'
import { ChevronRight } from 'lucide-react'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { isRecord, asString, asNumber } from './shared'
import type { ToolRenderContext } from './types'
import type { ToolResult } from '@/api/llm'

interface SearchCodeMatch {
  file?: string
  path?: string
  line?: number
  line_number?: number
  content?: string
  text?: string
  is_match?: boolean
}

const isSearchCodeMatch = (val: unknown): val is SearchCodeMatch => isRecord(val)

export function SearchCodeBody({ execution }: ToolRenderContext) {
  if (!execution.result || execution.isExecuting) return null

  const pattern: string | undefined = (() => {
    try { return JSON.parse(execution.tool_call.function.arguments)?.pattern } catch { return undefined }
  })()

  return <SearchCodeResult result={execution.result} pattern={pattern} />
}

// Component for displaying search_code results
const SearchCodeResult = memo(({ result, pattern }: { result: ToolResult, pattern?: string }) => {
  const [isExpanded, setIsExpanded] = useState(false)
  const { isDark } = useTheme()

  // Parse result
  const parsed = useMemo(() => {
    let data: unknown = result
    if (typeof data === 'string') {
      try { data = JSON.parse(data) } catch { return { matches: [] as SearchCodeMatch[], total: 0, error: null as string | null } }
    }
    // Unwrap nested result
    data = (isRecord(data) ? data.result : undefined) || data
    data = (isRecord(data) ? data.data : undefined) || data

    const rawMatches = isRecord(data) ? data.matches : undefined
    const matches = Array.isArray(rawMatches) ? rawMatches.filter(isSearchCodeMatch) : []
    const total = (isRecord(data) ? asNumber(data.total_matches) ?? asNumber(data.total) : undefined) ?? matches.length
    const error = (isRecord(data) ? asString(data.error) : undefined) || null

    return { matches, total, error }
  }, [result])

  const { matches, total, error } = parsed

  if (error) {
    return (
      <div className="ml-5 mt-1 text-xs text-red-400">
        <span className="text-muted-foreground/60 mr-1">⎿</span>
        {error}
      </div>
    )
  }

  if (matches.length === 0) {
    return (
      <div className="ml-5 mt-1 text-xs text-muted-foreground/60">
        <span className="mr-1">⎿</span>
        No matches found
      </div>
    )
  }

  return (
    <Collapsible open={isExpanded} onOpenChange={setIsExpanded} className="ml-5 mt-1">
      <CollapsibleTrigger className="flex items-center gap-1.5 text-xs text-muted-foreground/60 hover:text-muted-foreground transition-colors">
        <ChevronRight className={cn(
          "h-3 w-3 transition-transform duration-200",
          isExpanded && "rotate-90"
        )} />
        <span>{total} match{total !== 1 ? 'es' : ''}</span>
        {pattern && <code className="text-muted-foreground bg-muted/50 px-1 rounded">{pattern}</code>}
      </CollapsibleTrigger>

      <CollapsibleContent>
        <div className={cn(
          "mt-1.5 border rounded-md overflow-hidden max-h-[400px] overflow-y-auto",
          isDark ? "border-border/60 bg-card/50" : "border-border bg-white"
        )}>
          <div className="text-[11px] font-mono leading-[1.6]">
            {matches.map((match, idx) => {
              const file = match.file || match.path || ''
              const lineNum = match.line || match.line_number
              const content = match.content || match.text || ''
              const isMatch = match.is_match !== false

              return (
                <div
                  key={idx}
                  className={cn(
                    "flex border-b last:border-b-0",
                    isDark ? "border-border/30" : "border-slate-200",
                    isMatch
                      ? isDark ? "bg-amber-500/10" : "bg-amber-50"
                      : ""
                  )}
                >
                  {/* File:line number */}
                  <div className={cn(
                    "flex-shrink-0 w-48 px-2 py-0.5 border-r truncate",
                    isDark ? "border-border/30 text-blue-400" : "border-slate-200 text-blue-600"
                  )}>
                    {file}:{lineNum}
                  </div>
                  {/* Content */}
                  <pre className={cn(
                    "flex-1 px-2 py-0.5 whitespace-pre-wrap break-all",
                    isDark ? "text-muted-foreground" : "text-slate-700"
                  )}>
                    {content}
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
