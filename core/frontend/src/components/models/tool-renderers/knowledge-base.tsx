/** query_knowledge_base body: the ranked chunk results. */
import { memo, useState } from 'react'
import { cn } from '@/lib/utils'
import { useTheme } from '@/hooks/useTheme'
import { ChevronRight, ExternalLink } from 'lucide-react'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { TypeBadge } from '@/lib/type-badges'
import type { ToolRenderContext } from './types'

// Knowledge Base result type
interface KnowledgeBaseResult {
  chunk_id: string
  document_id: string
  document_filename: string
  document_type: string
  content: string
  full_content: string
  chunk_index: number
  page_number: number | null
  similarity_score: number
  token_count: number
}

interface KnowledgeBaseSearchData {
  query: string
  total_results: number
  results: KnowledgeBaseResult[]
  formatted_text: string
}

// Extract knowledge base results from tool result
const extractKnowledgeBaseResults = (executionResult: any): KnowledgeBaseSearchData | null => {
  let result = executionResult

  // If executionResult has a nested result property, use that
  if (executionResult && typeof executionResult === 'object' && 'result' in executionResult) {
    result = executionResult.result
  }

  // Parse result if it's a JSON string
  if (typeof result === 'string') {
    try {
      result = JSON.parse(result)
    } catch {
      // Result might be a simple string message (e.g., "No relevant documents found")
      return null
    }
  }

  // Check if this is a valid knowledge base result
  if (!result || typeof result !== 'object' || !result.results || !Array.isArray(result.results)) {
    return null
  }

  return {
    query: result.query || '',
    total_results: result.total_results || result.results.length,
    results: result.results,
    formatted_text: result.formatted_text || '',
  }
}

export function KnowledgeBaseBody(context: ToolRenderContext) {
  const { execution } = context
  if (!execution.result || execution.isExecuting || execution.success === false) return null

  const data = extractKnowledgeBaseResults(execution.result)
  if (!data) return null

  return <KnowledgeBaseResultsDisplay data={data} />
}

// Knowledge Base Results Display Component
const KnowledgeBaseResultsDisplay = memo(({ data }: { data: KnowledgeBaseSearchData }) => {
  const [expandedChunks, setExpandedChunks] = useState<Set<string>>(new Set())
  const { isDark } = useTheme()

  if (!data.results || data.results.length === 0) return null

  const toggleChunk = (chunkId: string) => {
    setExpandedChunks(prev => {
      const next = new Set(prev)
      if (next.has(chunkId)) {
        next.delete(chunkId)
      } else {
        next.add(chunkId)
      }
      return next
    })
  }

  return (
    <div className={cn(
      "mt-2 ml-5 border rounded-lg overflow-hidden",
      isDark ? "border-border/60 bg-card/30" : "border-border bg-white"
    )}>
      {/* Header */}
      <div className={cn(
        "px-3 py-2 border-b flex items-center justify-between",
        isDark ? "bg-emerald-500/10 border-border/50" : "bg-emerald-50 border-emerald-200"
      )}>
        <span className={cn("text-sm font-medium", isDark ? "text-emerald-400" : "text-emerald-700")}>
          {data.total_results} result{data.total_results !== 1 ? 's' : ''} found
        </span>
        <span className={cn("text-xs", isDark ? "text-muted-foreground/60" : "text-slate-500")}>
          "{data.query}"
        </span>
      </div>

      {/* Results list */}
      <div className="divide-y divide-border/50">
        {data.results.map((result, index) => {
          const isExpanded = expandedChunks.has(result.chunk_id)
          const similarityPercent = Math.round(result.similarity_score * 100)

          return (
            <Collapsible
              key={result.chunk_id || index}
              open={isExpanded}
              onOpenChange={() => toggleChunk(result.chunk_id)}
              className={cn(
                "transition-colors",
                isDark ? "hover:bg-muted/20" : "hover:bg-slate-50"
              )}
            >
              {/* Result header */}
              <CollapsibleTrigger className="w-full px-3 py-2 cursor-pointer text-left">
                <div className="flex items-start gap-2">
                  {/* Expand/collapse icon */}
                  <div className="flex-shrink-0 mt-0.5">
                    <ChevronRight className={cn(
                      "w-3.5 h-3.5 transition-transform duration-200",
                      isExpanded && "rotate-90",
                      isDark ? "text-muted-foreground" : "text-slate-400"
                    )} />
                  </div>

                  {/* Document info */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      {/* File type badge */}
                      <TypeBadge type={result.document_type} />

                      {/* Filename */}
                      <span className={cn(
                        "text-sm font-medium truncate",
                        isDark ? "text-foreground" : "text-slate-800"
                      )}>
                        {result.document_filename}
                      </span>

                      {/* Page number */}
                      {result.page_number && (
                        <span className={cn(
                          "text-xs",
                          isDark ? "text-muted-foreground/60" : "text-slate-500"
                        )}>
                          Page {result.page_number}
                        </span>
                      )}

                      {/* Similarity score */}
                      <span className={cn(
                        "ml-auto text-xs font-mono",
                        similarityPercent >= 80
                          ? isDark ? "text-emerald-400" : "text-emerald-600"
                          : similarityPercent >= 60
                            ? isDark ? "text-amber-400" : "text-amber-600"
                            : isDark ? "text-muted-foreground" : "text-slate-500"
                      )}>
                        {similarityPercent}% match
                      </span>
                    </div>

                    {/* Content preview (always shown) */}
                    {!isExpanded && (
                      <p className={cn(
                        "mt-1 text-xs line-clamp-2",
                        isDark ? "text-muted-foreground" : "text-slate-600"
                      )}>
                        {result.content}
                      </p>
                    )}
                  </div>
                </div>
              </CollapsibleTrigger>

              {/* Expanded content */}
              <CollapsibleContent>
                <div className={cn(
                  "px-3 pb-3 ml-6",
                  isDark ? "border-l border-border/30" : "border-l border-slate-200"
                )}>
                  {/* Full content */}
                  <div className={cn(
                    "p-3 rounded-md text-xs font-mono whitespace-pre-wrap",
                    isDark ? "bg-muted/30 text-muted-foreground" : "bg-slate-50 text-slate-700"
                  )}>
                    {result.full_content || result.content}
                  </div>

                  {/* Metadata footer */}
                  <div className={cn(
                    "mt-2 flex items-center gap-4 text-[10px]",
                    isDark ? "text-muted-foreground/50" : "text-slate-400"
                  )}>
                    <span>Chunk #{result.chunk_index + 1}</span>
                    <span>{result.token_count} tokens</span>
                    <a
                      href={`/knowledge?doc=${result.document_id}`}
                      className={cn(
                        "flex items-center gap-1 transition-colors",
                        isDark
                          ? "text-emerald-400/70 hover:text-emerald-400"
                          : "text-emerald-600/70 hover:text-emerald-600"
                      )}
                      onClick={(e) => e.stopPropagation()}
                    >
                      <ExternalLink className="w-3 h-3" />
                      View document
                    </a>
                  </div>
                </div>
              </CollapsibleContent>
            </Collapsible>
          )
        })}
      </div>
    </div>
  )
})
