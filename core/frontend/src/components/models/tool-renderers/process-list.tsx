/** list_processes body: the running-process table. */
import { memo } from 'react'
import { cn } from '@/lib/utils'
import { isRecord } from './shared'
import type { ToolRenderContext } from './types'
import type { ToolResult } from '@/api/llm'

interface ProcessListEntry {
  pid?: number
  command?: string
  name?: string
  port?: number
  status?: string
}

const isProcessListEntry = (val: unknown): val is ProcessListEntry => isRecord(val)

export function ProcessListBody({ execution }: ToolRenderContext) {
  if (!execution.result || execution.isExecuting) return null
  return <ProcessListDisplay result={execution.result} />
}

// Component for displaying list_processes results
const ProcessListDisplay = memo(({ result }: { result: ToolResult }) => {
  const data: unknown = (() => {
    try {
      if (typeof result === 'string') return JSON.parse(result)
      return result
    } catch { return null }
  })()

  const rawProcesses = isRecord(data) ? data.processes : undefined
  const processes = Array.isArray(rawProcesses) ? rawProcesses.filter(isProcessListEntry) : []
  if (processes.length === 0) return null

  return (
    <div className="space-y-0.5">
      <div className="text-xs text-muted-foreground/60 flex items-center mb-1">
        <span className="mr-1">⎿</span>
        <span>{processes.length} running process{processes.length !== 1 ? 'es' : ''}</span>
      </div>
      {processes.map((proc, idx) => (
        <div key={proc.pid || idx} className="flex items-center gap-3 text-xs py-0.5 ml-3 text-muted-foreground">
          <span className="font-mono text-muted-foreground/50 w-12 text-right shrink-0">
            {proc.pid || '—'}
          </span>
          <span className="font-mono truncate flex-1">
            {proc.command || proc.name || 'unknown'}
          </span>
          {proc.port && (
            <span className="text-muted-foreground/60 shrink-0">
              :{proc.port}
            </span>
          )}
          {proc.status && (
            <span className={cn(
              "text-xs shrink-0",
              proc.status === 'running' ? "text-emerald-500" : "text-muted-foreground/50"
            )}>
              {proc.status}
            </span>
          )}
        </div>
      ))}
    </div>
  )
})
