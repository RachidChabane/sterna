/** execute_code body: collapsible stdout/stderr plus any produced artifacts. */
import { useState } from 'react'
import { cn } from '@/lib/utils'
import { ChevronRight } from 'lucide-react'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { sanitizeOutput } from './shared'
import type { ToolRenderContext } from './types'

export function ExecuteCodeBody({ execution }: ToolRenderContext) {
  if (!execution.result || execution.isExecuting) return null
  return <ExecuteCodeResult result={execution.result} />
}

// Component for displaying execute_code results with collapsible output
// Modern inline style matching RunBashDisplay
const ExecuteCodeResult = ({ result }: { result: any }) => {
  const [isExpanded, setIsExpanded] = useState(false)

  // Parse result if it's a JSON string
  let parsedResult = result
  if (typeof result === 'string') {
    try {
      parsedResult = JSON.parse(result)
    } catch {
      parsedResult = { output: result, error: null, exit_code: 1, execution_time: 0 }
    }
  }

  // Extract the actual execution result (it's nested in result.result)
  const executionResult = parsedResult?.result || parsedResult
  const { output, error, exit_code, execution_time, artifacts } = executionResult

  // Get orchestrator URL from environment (routes through API Gateway)
  const orchestratorUrl = import.meta.env.VITE_ORCHESTRATOR_URL || 'http://localhost:8080/api/v1/sandbox'

  const displayOutput = output || error
  const hasOutput = !!displayOutput || (artifacts && artifacts.length > 0)
  const isError = exit_code !== 0

  return (
    <Collapsible open={isExpanded} onOpenChange={setIsExpanded} className="flex-1 min-w-0 mt-1">
      {/* Inline header - execution time and artifacts only (parent shows success/error status) */}
      <div className="flex items-center gap-1.5 min-w-0">
        <span className="text-sm flex items-center gap-1.5">
          {execution_time !== undefined && (
            <span className={cn(
              "text-xs font-mono",
              isError ? "text-red-400" : "text-muted-foreground"
            )}>
              {execution_time.toFixed(2)}s
            </span>
          )}
          {artifacts && artifacts.length > 0 && (
            <span className="text-muted-foreground text-xs">
              • {artifacts.length} file{artifacts.length > 1 ? 's' : ''}
            </span>
          )}
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

      {/* Expandable output - matches RunBashDisplay style */}
      {hasOutput && (
        <CollapsibleContent>
          <div className="mt-1 max-h-[400px] overflow-y-auto">
            {/* Artifacts (images, plots) */}
            {artifacts && artifacts.length > 0 && (
              <div className="space-y-2 mb-2">
                {artifacts.map((artifact: any, index: number) => {
                  const fullUrl = `${orchestratorUrl}${artifact.url}`
                  const filename = artifact.filename
                  return (
                    <div key={index} className="rounded border border-border/50 overflow-hidden bg-muted/30">
                      <div className="px-2 py-1 bg-muted/50 flex items-center justify-between">
                        <span className="text-xs font-mono text-muted-foreground">{filename}</span>
                        <a
                          href={fullUrl}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-xs text-accent-brand hover:text-accent-brand/80"
                        >
                          Open
                        </a>
                      </div>
                      <div className="p-2">
                        <img
                          src={fullUrl}
                          alt={filename}
                          className="max-w-full h-auto rounded"
                          onError={(e) => {
                            (e.target as HTMLImageElement).style.display = 'none'
                          }}
                        />
                      </div>
                    </div>
                  )
                })}
              </div>
            )}

            {/* Text/Error output */}
            {displayOutput && (
              <div className="flex">
                <span className="text-muted-foreground/60 mr-1 text-xs">⎿</span>
                <pre className={cn(
                  "text-xs font-mono whitespace-pre-wrap max-h-[300px] overflow-y-auto",
                  isError ? "text-red-400" : "text-muted-foreground"
                )}>
                  {sanitizeOutput(displayOutput)}
                </pre>
              </div>
            )}
          </div>
        </CollapsibleContent>
      )}
    </Collapsible>
  )
}
