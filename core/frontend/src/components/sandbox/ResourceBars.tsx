/**
 * ResourceBars - Compact storage and RAM usage indicators for the IDE top bar.
 * Connects via WebSocket for real-time push updates from the orchestrator.
 * Falls back to HTTP polling if the WebSocket cannot connect.
 */

import { useState, useEffect, useRef } from 'react'
import { HardDrive, MemoryStick } from 'lucide-react'
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import { cn } from '@/lib/utils'
import { getAccessToken, ORCHESTRATOR_URL } from '@/api/client'
import { fsAPI } from '@/api/fs'

interface ResourceBarsProps {
  userId?: string
  chatId?: string
  className?: string
}

interface ResourceStats {
  storage_used_mb: number
  storage_total_mb: number
  storage_percent: number
  memory_used_mb: number
  memory_total_mb: number
  memory_percent: number
}

function getBarColor(percent: number): string {
  if (percent >= 90) return 'bg-red-500'
  if (percent >= 70) return 'bg-amber-500'
  return 'bg-accent-brand'
}

function getTextColor(percent: number): string {
  if (percent >= 90) return 'text-red-500 dark:text-red-400'
  if (percent >= 70) return 'text-amber-500 dark:text-amber-400'
  return 'text-muted-foreground'
}

function formatMB(mb: number): string {
  if (mb >= 1024) return `${(mb / 1024).toFixed(1)} GB`
  return `${Math.round(mb)} MB`
}

function MiniBar({ percent, label, icon: Icon, used, total, className }: {
  percent: number
  label: string
  icon: typeof HardDrive
  used: number
  total: number
  className?: string
}) {
  return (
    <TooltipProvider delayDuration={200}>
      <Tooltip>
        <TooltipTrigger asChild>
          <div className={cn('flex items-center gap-1.5 cursor-default select-none', className)}>
            <Icon className={cn('h-3 w-3 shrink-0', getTextColor(percent))} />
            <div className="w-16 h-1.5 rounded-full bg-muted overflow-hidden">
              <div
                className={cn('h-full rounded-full transition-all duration-500 ease-out', getBarColor(percent))}
                style={{ width: `${Math.min(percent, 100)}%` }}
              />
            </div>
            <span className={cn('text-[10px] tabular-nums font-medium', getTextColor(percent))}>
              {Math.round(percent)}%
            </span>
          </div>
        </TooltipTrigger>
        <TooltipContent side="bottom" className="text-xs">
          <p className="font-medium">{label}</p>
          <p className="text-muted-foreground">
            {formatMB(used)} / {formatMB(total)}
          </p>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  )
}

/** Build the WebSocket URL from the orchestrator HTTP URL. */
function buildWsUrl(userId: string, chatId: string, token: string): string {
  // ORCHESTRATOR_URL is like "/api/v1/sandbox" or "http://host:port"
  let base = ORCHESTRATOR_URL
  if (base.startsWith('/')) {
    // Relative — derive from current origin
    const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    base = `${proto}//${window.location.host}${base}`
  } else {
    base = base.replace(/^http/, 'ws')
  }
  // Remove trailing slash
  base = base.replace(/\/$/, '')
  return `${base}/ws/workspace/stats?token=${encodeURIComponent(token)}&user_id=${encodeURIComponent(userId)}&chat_id=${encodeURIComponent(chatId)}`
}

export function ResourceBars({ userId, chatId, className }: ResourceBarsProps) {
  const [stats, setStats] = useState<ResourceStats | null>(null)
  const wsRef = useRef<WebSocket | null>(null)
  const fallbackRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    if (!userId || !chatId) return

    const token = getAccessToken()
    if (!token) return

    let disposed = false
    let reconnectDelay = 2000

    function connectWs() {
      if (disposed) return

      try {
        const url = buildWsUrl(userId!, chatId!, token!)
        const ws = new WebSocket(url)
        wsRef.current = ws

        ws.onopen = () => {
          reconnectDelay = 2000 // reset on successful connect
          // Stop HTTP fallback if it was running
          if (fallbackRef.current) {
            clearInterval(fallbackRef.current)
            fallbackRef.current = null
          }
        }

        ws.onmessage = (event) => {
          try {
            const data = JSON.parse(event.data)
            if (data.type === 'stats') {
              setStats({
                storage_used_mb: data.storage_used_mb,
                storage_total_mb: data.storage_total_mb,
                storage_percent: data.storage_percent,
                memory_used_mb: data.memory_used_mb,
                memory_total_mb: data.memory_total_mb,
                memory_percent: data.memory_percent,
              })
            }
          } catch {
            // ignore malformed frames
          }
        }

        ws.onclose = () => {
          wsRef.current = null
          if (!disposed) {
            // Start HTTP fallback while reconnecting
            startHttpFallback()
            // Reconnect with backoff
            reconnectTimerRef.current = setTimeout(() => {
              reconnectDelay = Math.min(reconnectDelay * 1.5, 30000)
              connectWs()
            }, reconnectDelay)
          }
        }

        ws.onerror = () => {
          // onclose will fire after onerror, triggering reconnect
        }
      } catch {
        // WebSocket constructor failed — use HTTP fallback
        startHttpFallback()
      }
    }

    function startHttpFallback() {
      if (disposed || fallbackRef.current) return
      fetchOnce() // immediate first fetch
      fallbackRef.current = setInterval(fetchOnce, 15000)
    }

    async function fetchOnce() {
      if (disposed) return
      try {
        const result = await fsAPI.getWorkspaceStats({ user_id: userId!, chat_id: chatId! })
        if (result.success) {
          setStats({
            storage_used_mb: result.storage_used_mb,
            storage_total_mb: result.storage_total_mb,
            storage_percent: result.storage_percent,
            memory_used_mb: result.memory_used_mb,
            memory_total_mb: result.memory_total_mb,
            memory_percent: result.memory_percent,
          })
        }
      } catch {
        // informational only
      }
    }

    connectWs()

    return () => {
      disposed = true
      if (wsRef.current) {
        wsRef.current.close()
        wsRef.current = null
      }
      if (fallbackRef.current) {
        clearInterval(fallbackRef.current)
        fallbackRef.current = null
      }
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current)
        reconnectTimerRef.current = null
      }
    }
  }, [userId, chatId])

  if (!stats) return null

  return (
    <div className={cn(
      'flex items-center gap-3 px-3 py-1 border-b border-border/40 bg-muted/20',
      className,
    )}>
      <MiniBar
        percent={stats.storage_percent}
        label="Storage"
        icon={HardDrive}
        used={stats.storage_used_mb}
        total={stats.storage_total_mb}
      />
      <MiniBar
        percent={stats.memory_percent}
        label="Memory"
        icon={MemoryStick}
        used={stats.memory_used_mb}
        total={stats.memory_total_mb}
      />
    </div>
  )
}
