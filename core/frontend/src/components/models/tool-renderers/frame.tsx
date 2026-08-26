/**
 * ToolFrame — the shared wrapper every framed tool renders inside: the
 * outer row (status spinner + header content) and the "failed" indicator,
 * with an optional body section below the row.
 *
 * Owns exactly the DOM FileToolExecutionsDisplay used to own around each
 * tool's own content: renderers never add their own outer wrapper.
 */
import type { ReactNode } from 'react'
import { Loader2 } from 'lucide-react'
import { cn } from '@/lib/utils'
import type { ToolRenderContext } from './types'

interface ToolFrameProps {
  context: ToolRenderContext
  header: ReactNode
  body?: ReactNode
  suppressErrorRow?: boolean
}

export function ToolFrame({ context, header, body, suppressErrorRow }: ToolFrameProps) {
  const { execution, isCodeVariant, effectiveSuccess } = context

  return (
    <div className="space-y-0">
      {/* Header Row - Clean style */}
      <div className={cn(
        "flex items-start gap-2 py-0.5 text-xs",
        isCodeVariant && "text-muted-foreground"
      )}>
        {/* Status Icon - only show spinner while executing */}
        {execution.isExecuting && (
          <div className="flex-shrink-0 flex items-center justify-center mt-0.5">
            <Loader2 className={cn(
              "animate-spin",
              isCodeVariant ? "w-1.5 h-1.5 text-muted-foreground" : "w-3.5 h-3.5 text-accent-brand"
            )} />
          </div>
        )}

        {/* Content - varies by tool type */}
        <div className="flex-1 min-w-0">
          {header}

          {/* Error indicator */}
          {!execution.isExecuting && effectiveSuccess === false && !suppressErrorRow && (
            <div className="text-red-400 text-xs flex items-center">
              <span className="text-muted-foreground/60 mr-1">⎿</span>failed
            </div>
          )}
        </div>
      </div>

      {body}
    </div>
  )
}
