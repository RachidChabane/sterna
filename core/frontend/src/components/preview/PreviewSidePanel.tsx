/**
 * PreviewSidePanel Component
 *
 * Independent side panel for previewing sandbox dev server processes.
 * Works without requiring a cloned GitHub repo.
 */

import { useState, useCallback, useEffect, useRef } from 'react'
import {
  X,
  ArrowLeft,
  Globe,
  GripVertical,
  Loader2,
  ChevronRight,
  RefreshCw,
  Square,
  RotateCcw,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { usePreviewPanelStore } from '@/store/previewPanelStore'
import { useAuthStore } from '@/store/authStore'
import { Button } from '@/components/ui/button'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { useUIStore } from '@/store/uiStore'
import { fetchPreviewToken, getPreviewUrl, stopProcessByPort, restartProcess, listProcesses, type ProcessInfo } from '@/api/sandbox'

interface PreviewSidePanelProps {
  conversationId: string
  chatId?: string
  className?: string
}

const MIN_PANEL_WIDTH = 400
const MAX_PANEL_WIDTH = 1200
// Match Spark preview width: half the viewport (same as ArtifactsSidePanel sparkOpenWidth)
const getDefaultPanelWidth = () =>
  typeof window !== 'undefined' ? Math.max(MIN_PANEL_WIDTH, Math.floor(window.innerWidth / 2)) : 700

function PreviewContent({ conversationId, chatId }: { conversationId: string; chatId?: string }) {
  const { previewPort, setPreviewPort } = usePreviewPanelStore()
  const { user } = useAuthStore()
  const userId = user?.id?.toString()
  const [previewToken, setPreviewToken] = useState<string | null>(null)
  const [tokenLoading, setTokenLoading] = useState(false)
  const [status, setStatus] = useState<'running' | 'stopped' | 'restarting'>('running')
  const [lastCommand, setLastCommand] = useState<string | null>(null)
  const [processes, setProcesses] = useState<ProcessInfo[]>([])
  const [processesLoading, setProcessesLoading] = useState(false)
  const [selectedPort, setSelectedPort] = useState<number | null>(null)
  const iframeRef = useRef<HTMLIFrameElement>(null)

  // Fetch running processes — auto-select if only one
  const fetchProcesses = useCallback(async () => {
    if (!userId || !chatId) return
    setProcessesLoading(true)
    try {
      const procs = await listProcesses(userId, chatId)
      setProcesses(procs)
      if (selectedPort && !procs.some(p => p.port === selectedPort)) {
        setSelectedPort(null)
      }
      // Auto-select when there's exactly one process and none selected yet
      if (!selectedPort && procs.length === 1) {
        setSelectedPort(procs[0].port)
        setPreviewPort(procs[0].port)
        setLastCommand(procs[0].command || null)
        setStatus('running')
      }
    } catch {
      // ignore
    } finally {
      setProcessesLoading(false)
    }
  }, [userId, chatId, selectedPort, setPreviewPort])

  // Fetch on mount
  useEffect(() => {
    fetchProcesses()
  }, [fetchProcesses])

  // Listen for preview:started — auto-select the started port directly
  useEffect(() => {
    const handler = (event: CustomEvent<{ port: number; command: string; pid: number }>) => {
      const { port, command } = event.detail
      setSelectedPort(port)
      setPreviewPort(port)
      setLastCommand(command || null)
      setStatus('running')
      fetchProcesses()
    }
    window.addEventListener('preview:started', handler as EventListener)
    return () => window.removeEventListener('preview:started', handler as EventListener)
  }, [fetchProcesses, setPreviewPort])

  // Fetch preview token when selected port changes
  useEffect(() => {
    if (!selectedPort || !userId) {
      setPreviewToken(null)
      setTokenLoading(false)
      return
    }

    let cancelled = false
    setTokenLoading(true)

    const fetchToken = async () => {
      try {
        const token = await fetchPreviewToken(userId, selectedPort)
        if (!cancelled) {
          setPreviewToken(token)
          setTokenLoading(false)
        }
      } catch {
        if (!cancelled) {
          setPreviewToken(null)
          setTokenLoading(false)
        }
      }
    }

    fetchToken()
    const refreshTimer = setInterval(fetchToken, 4 * 60 * 1000)

    return () => {
      cancelled = true
      clearInterval(refreshTimer)
    }
  }, [selectedPort, userId])

  const handleSelectProcess = (proc: ProcessInfo) => {
    setSelectedPort(proc.port)
    setPreviewPort(proc.port)
    setLastCommand(proc.command || null)
    setStatus('running')
  }

  const handleBack = () => {
    setSelectedPort(null)
    setPreviewToken(null)
    fetchProcesses()
  }

  const handleStop = async () => {
    if (!userId || !selectedPort) return
    try {
      await stopProcessByPort(userId, conversationId, selectedPort)
      setProcesses(prev => prev.filter(p => p.port !== selectedPort))
      setSelectedPort(null)
    } catch (e) {
      console.error('Failed to stop preview:', e)
    }
  }

  const handleRestart = async () => {
    if (!userId || !selectedPort || !lastCommand) return
    try {
      setStatus('restarting')
      await restartProcess({
        user_id: userId,
        conversation_id: conversationId,
        chat_id: chatId,
        command: lastCommand,
        port: selectedPort,
      })
      setStatus('running')
      const token = await fetchPreviewToken(userId, selectedPort)
      setPreviewToken(token)
    } catch (e) {
      console.error('Failed to restart preview:', e)
      setStatus('stopped')
    }
  }

  // -- Process selector view (no port selected yet) --
  if (!selectedPort) {
    if (processesLoading) {
      return (
        <div className="flex items-center justify-center py-16">
          <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
        </div>
      )
    }

    if (processes.length === 0) {
      return (
        <div className="flex flex-col items-center justify-center py-16 px-6 text-center">
          <div className="w-10 h-10 rounded-lg bg-muted/50 flex items-center justify-center mb-3">
            <Globe className="w-5 h-5 text-muted-foreground/40" />
          </div>
          <p className="text-sm text-muted-foreground">No dev server running</p>
          <p className="text-xs text-muted-foreground/60 mt-1">A live preview will appear here when the coding agent starts a dev server in the sandbox</p>
        </div>
      )
    }

    return (
      <div className="flex flex-col gap-1 p-3">
        <div className="flex items-center justify-between mb-2">
          <span className="text-xs font-medium text-muted-foreground">
            {processes.length} running process{processes.length !== 1 ? 'es' : ''}
          </span>
          <Button variant="ghost" size="sm" className="h-6 px-2 text-[11px]" onClick={fetchProcesses}>
            <RefreshCw className="h-3 w-3" />
          </Button>
        </div>
        {processes.map((proc) => (
          <button
            key={proc.port}
            className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg border border-border/40 hover:bg-muted/50 transition-colors text-left group"
            onClick={() => handleSelectProcess(proc)}
          >
            <div className="h-2 w-2 rounded-full bg-green-500 animate-pulse shrink-0" />
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <span className="font-mono text-sm font-medium">:{proc.port}</span>
              </div>
              <p className="text-xs text-muted-foreground truncate mt-0.5">{proc.command}</p>
            </div>
            <ChevronRight className="h-4 w-4 text-muted-foreground/40 group-hover:text-foreground shrink-0 transition-colors" />
          </button>
        ))}
      </div>
    )
  }

  // -- Preview view (port selected) --
  return (
    <div className="flex flex-col h-full">
      {/* Controls bar */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-border/40 shrink-0">
        <div className="flex items-center gap-2 text-sm min-w-0">
          <button onClick={handleBack} className="hover:bg-muted/50 rounded p-0.5 transition-colors shrink-0">
            <ChevronRight className="h-3.5 w-3.5 rotate-180 text-muted-foreground" />
          </button>
          <div className={cn(
            "h-2 w-2 rounded-full shrink-0",
            status === 'running' ? "bg-green-500 animate-pulse" :
            status === 'restarting' ? "bg-yellow-500 animate-pulse" :
            "bg-muted-foreground"
          )} />
          <span className="font-mono text-xs">localhost:{selectedPort}</span>
          {status === 'stopped' && <span className="text-muted-foreground text-xs">(stopped)</span>}
        </div>
        <div className="flex items-center gap-1">
          {status === 'running' && (
            <Button variant="ghost" size="sm" className="h-6 px-2 text-[11px]" onClick={handleStop}>
              <Square className="h-3 w-3 mr-1" /> Stop
            </Button>
          )}
          {lastCommand && (
            <Button variant="ghost" size="sm" className="h-6 px-2 text-[11px]" onClick={handleRestart}
              disabled={status === 'restarting'}>
              <RotateCcw className={cn("h-3 w-3 mr-1", status === 'restarting' && "animate-spin")} />
              {status === 'restarting' ? 'Restarting...' : 'Restart'}
            </Button>
          )}
        </div>
      </div>

      {/* Preview iframe */}
      <div className="flex-1 overflow-hidden bg-white">
        {tokenLoading ? (
          <div className="flex items-center justify-center h-full">
            <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
          </div>
        ) : previewToken && userId ? (
          <iframe
            ref={iframeRef}
            src={getPreviewUrl(userId, selectedPort, previewToken)}
            className="w-full h-full border-0"
            sandbox="allow-scripts allow-same-origin allow-forms allow-popups"
            title={`Preview port ${selectedPort}`}
          />
        ) : (
          <div className="flex items-center justify-center h-full text-sm text-muted-foreground">
            Failed to load preview
          </div>
        )}
      </div>
    </div>
  )
}

export function PreviewSidePanel({ conversationId, chatId, className }: PreviewSidePanelProps) {
  const { isPanelOpen, closePanel, openPanel, setPreviewPort } = usePreviewPanelStore()
  const isMobile = useUIStore((state) => state.isMobile)

  // Resizable panel state
  const [panelWidth, setPanelWidth] = useState(getDefaultPanelWidth)
  const [isResizing, setIsResizing] = useState(false)
  const resizeRef = useRef<HTMLDivElement>(null)

  // Listen for preview:started events and auto-open panel
  useEffect(() => {
    const handlePreviewStarted = (event: CustomEvent<{ port: number; command: string; pid: number }>) => {
      const { port } = event.detail
      setPreviewPort(port)
      openPanel()
    }
    window.addEventListener('preview:started', handlePreviewStarted as EventListener)
    return () => window.removeEventListener('preview:started', handlePreviewStarted as EventListener)
  }, [setPreviewPort, openPanel])

  // Handle resize drag
  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      if (!isResizing) return
      const newWidth = window.innerWidth - e.clientX
      setPanelWidth(Math.min(MAX_PANEL_WIDTH, Math.max(MIN_PANEL_WIDTH, newWidth)))
    }

    const handleMouseUp = () => {
      setIsResizing(false)
      document.body.style.cursor = ''
      document.body.style.userSelect = ''
    }

    if (isResizing) {
      document.body.style.cursor = 'col-resize'
      document.body.style.userSelect = 'none'
      document.addEventListener('mousemove', handleMouseMove)
      document.addEventListener('mouseup', handleMouseUp)
    }

    return () => {
      document.removeEventListener('mousemove', handleMouseMove)
      document.removeEventListener('mouseup', handleMouseUp)
    }
  }, [isResizing])

  const handleResizeStart = useCallback((e: React.MouseEvent) => {
    e.preventDefault()
    setIsResizing(true)
  }, [])

  // Mobile: Fullscreen overlay
  if (isMobile) {
    if (!isPanelOpen) return null
    return (
      <div className="fixed inset-0 z-50 bg-background flex flex-col">
        {/* Slim toolbar */}
        <div className="flex items-center gap-2 px-3 py-2.5 border-b border-border/40 shrink-0">
          <button
            onClick={closePanel}
            className="p-1.5 -ml-1 rounded-md hover:bg-muted transition-colors"
          >
            <ArrowLeft className="h-5 w-5" />
          </button>
          <Globe className="h-4 w-4 text-muted-foreground shrink-0" />
          <span className="font-medium text-sm">Dev Server</span>
        </div>

        {/* Content takes full remaining height */}
        <div className="flex-1 overflow-hidden">
          <PreviewContent conversationId={conversationId} chatId={chatId} />
        </div>
      </div>
    )
  }

  // Desktop: Side panel
  return (
    <div
      className={cn(
        'h-full flex flex-col relative overflow-hidden',
        'transition-[width] duration-300 ease-in-out',
        className
      )}
      style={{ width: isPanelOpen ? panelWidth : 0 }}
    >
      <div
        className={cn(
          'h-full border-l border-border/40 bg-card flex flex-col relative',
          'transition-transform duration-300 ease-in-out',
          isPanelOpen ? 'translate-x-0' : 'translate-x-full'
        )}
        style={{ width: panelWidth }}
      >
        {/* Resize handle */}
        <div
          ref={resizeRef}
          onMouseDown={handleResizeStart}
          className={cn(
            'absolute left-0 top-0 bottom-0 w-1 cursor-col-resize z-10',
            'hover:bg-primary/20 transition-colors group flex items-center justify-center',
            isResizing && 'bg-primary/30'
          )}
        >
          <div
            className={cn(
              'absolute left-0 w-4 h-12 flex items-center justify-center',
              'opacity-0 group-hover:opacity-100 transition-opacity',
              isResizing && 'opacity-100'
            )}
          >
            <GripVertical className="w-3 h-3 text-muted-foreground" />
          </div>
        </div>

        {/* Header */}
        <div className="flex items-center justify-between p-3 border-b border-border/40">
          <TooltipProvider delayDuration={300}>
            <Tooltip>
              <TooltipTrigger asChild>
                <span className="font-medium text-sm cursor-default">Dev Server</span>
              </TooltipTrigger>
              <TooltipContent side="bottom"><p>Live preview of running sandbox processes (dev servers, builds, etc.)</p></TooltipContent>
            </Tooltip>
            <Tooltip>
              <TooltipTrigger asChild>
                <Button variant="ghost" size="icon" className="h-7 w-7" onClick={closePanel}>
                  <X className="h-4 w-4" />
                </Button>
              </TooltipTrigger>
              <TooltipContent side="bottom"><p>Close panel</p></TooltipContent>
            </Tooltip>
          </TooltipProvider>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-hidden">
          <PreviewContent conversationId={conversationId} chatId={chatId} />
        </div>
      </div>
    </div>
  )
}
