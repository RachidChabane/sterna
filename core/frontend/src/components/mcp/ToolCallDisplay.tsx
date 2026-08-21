/**
 * ToolCallDisplay Component
 *
 * Displays an executed MCP tool call in an expandable block.
 * Similar to reasoning display - shows tool name, arguments, result, and execution status.
 * Color-coded based on execution status (success/error).
 */

import { useState } from 'react'
import {
  Wrench,
  ChevronDown,
  ChevronUp,
  CheckCircle2,
  XCircle,
  Clock,
  Loader2,
} from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'
import type { MCPToolExecution } from '@/api/mcp'

interface ToolCallDisplayProps {
  execution: MCPToolExecution
  className?: string
}

export function ToolCallDisplay({ execution, className }: ToolCallDisplayProps) {
  const [expanded, setExpanded] = useState(false)

  const getStatusIcon = () => {
    switch (execution.status) {
      case 'success':
        return <CheckCircle2 className="h-4 w-4 text-green-600 dark:text-green-400" />
      case 'error':
        return <XCircle className="h-4 w-4 text-red-600 dark:text-red-400" />
      case 'running':
        return <Loader2 className="h-4 w-4 text-blue-600 dark:text-blue-400 animate-spin" />
      default:
        return <Clock className="h-4 w-4 text-muted-foreground" />
    }
  }

  const getStatusBadge = () => {
    switch (execution.status) {
      case 'success':
        return (
          <Badge
            variant="outline"
            className="bg-green-500/10 border-green-500/50 text-green-700 dark:text-green-400"
          >
            Success
          </Badge>
        )
      case 'error':
        return (
          <Badge
            variant="outline"
            className="bg-red-500/10 border-red-500/50 text-red-700 dark:text-red-400"
          >
            Error
          </Badge>
        )
      case 'running':
        return (
          <Badge
            variant="outline"
            className="bg-blue-500/10 border-blue-500/50 text-blue-700 dark:text-blue-400"
          >
            Running
          </Badge>
        )
      default:
        return (
          <Badge variant="outline" className="text-xs">
            {execution.status}
          </Badge>
        )
    }
  }

  const getBorderColor = () => {
    switch (execution.status) {
      case 'success':
        return 'border-green-500/30'
      case 'error':
        return 'border-red-500/30'
      case 'running':
        return 'border-blue-500/30'
      default:
        return 'border-border'
    }
  }

  const getBgColor = () => {
    switch (execution.status) {
      case 'success':
        return 'bg-green-500/5'
      case 'error':
        return 'bg-red-500/5'
      case 'running':
        return 'bg-blue-500/5'
      default:
        return 'bg-muted/50'
    }
  }

  return (
    <div
      className={cn(
        "my-3 rounded-lg border p-3 space-y-2",
        getBorderColor(),
        getBgColor(),
        className
      )}
    >
      {/* Header - Always visible */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex items-center justify-between w-full text-left gap-2 hover:opacity-80 transition-opacity"
      >
        <div className="flex items-center gap-2 flex-1 min-w-0">
          <Wrench className="h-4 w-4 text-blue-600 dark:text-blue-400 flex-shrink-0" />
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium truncate">
              {execution.tool_name || 'Unknown Tool'}
            </p>
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              {execution.duration_ms !== undefined && (
                <span>{execution.duration_ms}ms</span>
              )}
              {execution.completed_at && (
                <span>
                  {new Date(execution.completed_at).toLocaleTimeString()}
                </span>
              )}
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {getStatusIcon()}
          {getStatusBadge()}
          {expanded ? (
            <ChevronUp className="h-4 w-4 text-muted-foreground" />
          ) : (
            <ChevronDown className="h-4 w-4 text-muted-foreground" />
          )}
        </div>
      </button>

      {/* Expandable Content */}
      {expanded && (
        <div className="space-y-3 pt-2 border-t">
          {/* Arguments */}
          {execution.arguments && Object.keys(execution.arguments).length > 0 && (
            <div className="space-y-1.5">
              <p className="text-xs font-medium text-muted-foreground">Arguments:</p>
              <div className="rounded bg-muted/50 p-2 text-xs font-mono space-y-1">
                {Object.entries(execution.arguments).map(([key, value]) => (
                  <div key={key} className="flex gap-2">
                    <span className="text-muted-foreground">{key}:</span>
                    <span className="flex-1 break-all">
                      {typeof value === 'string'
                        ? value
                        : JSON.stringify(value, null, 2)}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Result */}
          {execution.status === 'success' && execution.result && (
            <div className="space-y-1.5">
              <p className="text-xs font-medium text-muted-foreground">Result:</p>
              <div className="rounded bg-muted/50 p-2 text-xs font-mono whitespace-pre-wrap break-all max-h-[300px] overflow-y-auto">
                {typeof execution.result === 'string'
                  ? execution.result
                  : JSON.stringify(execution.result, null, 2)}
              </div>
            </div>
          )}

          {/* Error */}
          {execution.status === 'error' && execution.error_message && (
            <div className="space-y-1.5">
              <p className="text-xs font-medium text-red-600 dark:text-red-400">Error:</p>
              <div className="rounded bg-red-500/10 border border-red-500/30 p-2 text-xs">
                <p className="text-red-700 dark:text-red-300">{execution.error_message}</p>
              </div>
            </div>
          )}

          {/* Execution metadata */}
          <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground pt-1 border-t">
            {execution.started_at && (
              <span>Started: {new Date(execution.started_at).toLocaleString()}</span>
            )}
            {execution.completed_at && (
              <span>Completed: {new Date(execution.completed_at).toLocaleString()}</span>
            )}
            {execution.session_id && (
              <span className="font-mono">Session: {execution.session_id.slice(0, 8)}</span>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
