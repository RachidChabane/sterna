import { useState, useEffect, useCallback, useRef } from 'react'
import { useNavigate } from '@tanstack/react-router'
import {
  ArrowLeft,
  ChevronLeft,
  ChevronRight,
  ExternalLink,
  Loader2,
  Play,
  Rocket,
  Search,
  Square,
  X,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { useToast } from '@/hooks/use-toast'
import { useNavigationStore } from '@/store/navigationStore'
import { Globe, RefreshCw } from 'lucide-react'
import { useAppsStore } from '@/store/appsStore'
import { appsAPI, type AppListItem, type App } from '@/api/apps'
import { useAuthStore } from '@/store/authStore'
import { fetchPreviewToken, getPreviewUrl, checkProcessHealth } from '@/api/sandbox'
import { PremiumMenuIcon } from '@/components/ui/premium-menu-icon'

const PAGE_SIZE = 12

export function AppsGalleryPage({ embedded }: { embedded?: boolean }) {
  const navigate = useNavigate()
  const { openMobileSidebar } = useNavigationStore()
  const { toast } = useToast()

  const [apps, setApps] = useState<AppListItem[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [page, setPage] = useState(1)
  const [totalCount, setTotalCount] = useState(0)
  const [hasNext, setHasNext] = useState(false)
  const [hasPrevious, setHasPrevious] = useState(false)

  const [searchQuery, setSearchQuery] = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')

  const [selectedApp, setSelectedApp] = useState<App | null>(null)

  const previewStates = useAppsStore((s) => s.previewStates)
  const setPreviewState = useAppsStore((s) => s.setPreviewState)
  const clearPreviewState = useAppsStore((s) => s.clearPreviewState)

  // Debounce search
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearch(searchQuery)
      setPage(1)
    }, 300)
    return () => clearTimeout(timer)
  }, [searchQuery])

  const loadApps = useCallback(async () => {
    setIsLoading(true)
    try {
      const response = await appsAPI.list({ page, page_size: PAGE_SIZE })
      setApps(response.results)
      setTotalCount(response.count)
      setHasNext(response.next !== null)
      setHasPrevious(response.previous !== null)
    } catch {
      toast({ title: 'Failed to load Apps', variant: 'destructive' })
    } finally {
      setIsLoading(false)
    }
  }, [page, toast])

  useEffect(() => { loadApps() }, [loadApps])

  // Cleanup on unmount / tab close
  useEffect(() => {
    const cleanup = () => {
      const { previewStates: states } = useAppsStore.getState()
      Object.entries(states).forEach(([appId, state]) => {
        if (state.running) {
          appsAPI.stopPreview(appId, state.port ?? undefined).catch(() => {})
        }
      })
      useAppsStore.getState().clearAllPreviews()
    }
    window.addEventListener('beforeunload', cleanup)
    return () => {
      window.removeEventListener('beforeunload', cleanup)
      cleanup()
    }
  }, [])

  // Client-side search filter
  const filteredApps = debouncedSearch
    ? apps.filter((a) => a.title.toLowerCase().includes(debouncedSearch.toLowerCase()))
    : apps

  const totalPages = Math.ceil(totalCount / PAGE_SIZE)

  const handleSelectApp = useCallback(async (appId: string) => {
    const app = await appsAPI.get(appId)
    if (app) setSelectedApp(app)
  }, [])

  return (
    <div className="h-full flex flex-col overflow-hidden bg-background">
      {selectedApp ? (
        <AppDetailView
          app={selectedApp}
          onBack={() => setSelectedApp(null)}
        />
      ) : (
        <>
          {/* Mobile header */}
          {!embedded && (
            <div className="md:hidden flex items-center justify-between px-4 py-3 border-b border-border/50 sticky top-0 z-40 bg-background/95 backdrop-blur">
              <button onClick={openMobileSidebar} className="p-2 -ml-2 text-foreground transition-colors">
                <PremiumMenuIcon size={18} />
              </button>
              <h1 className="text-base font-medium text-foreground">Apps</h1>
              <div className="w-8" />
            </div>
          )}

          {/* Desktop header */}
          <div className="flex-1 overflow-y-auto">
            <div className="sticky top-0 z-30 bg-background hidden md:block">
              <div className={cn("max-w-6xl mx-auto px-4 sm:px-6 pb-5", embedded ? "pt-4" : "pt-8")}>
                {!embedded && (
                  <div className="flex items-center justify-between gap-4">
                    <h1 className="text-2xl font-semibold tracking-tight text-foreground">Apps</h1>
                  </div>
                )}
                <div className={cn("flex items-center gap-3", !embedded && "mt-5")}>
                  <div className="relative ml-auto w-56">
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground pointer-events-none" />
                    <input
                      type="text"
                      value={searchQuery}
                      onChange={(e) => setSearchQuery(e.target.value)}
                      placeholder="Search..."
                      className="w-full h-8 pl-9 pr-8 rounded-full bg-transparent border border-border/50 text-sm placeholder:text-muted-foreground/60 focus:outline-none focus:ring-1 focus:ring-ring focus:border-ring transition-colors"
                      maxLength={200}
                    />
                    {searchQuery && (
                      <button onClick={() => setSearchQuery('')} className="absolute right-2.5 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground">
                        <X className="h-3.5 w-3.5" />
                      </button>
                    )}
                  </div>
                </div>
              </div>
            </div>

            {/* Mobile search */}
            <div className="md:hidden px-4 py-3 space-y-2.5 border-b border-border/30 sticky top-0 z-20 bg-background">
              <div className="relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground pointer-events-none" />
                <input
                  type="text"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="Search apps..."
                  className="w-full h-9 pl-9 pr-9 rounded-lg bg-muted/50 border border-border/50 text-sm placeholder:text-muted-foreground/60 focus:outline-none focus:ring-1 focus:ring-ring focus:border-ring transition-colors"
                  maxLength={200}
                />
                {searchQuery && (
                  <button onClick={() => setSearchQuery('')} className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground">
                    <X className="h-3.5 w-3.5" />
                  </button>
                )}
              </div>
            </div>

            {/* Grid */}
            <div className="max-w-6xl mx-auto px-4 sm:px-6 py-6 pb-24 md:pb-10">
              {isLoading && apps.length === 0 ? (
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-x-5 gap-y-8">
                  {Array.from({ length: 6 }).map((_, i) => (
                    <div key={i}>
                      <Skeleton className="aspect-[16/10] rounded-xl" />
                      <Skeleton className="h-4 w-2/3 mt-2.5" />
                    </div>
                  ))}
                </div>
              ) : filteredApps.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-20 px-6">
                  <div className="w-12 h-12 rounded-full bg-muted/60 flex items-center justify-center mb-4">
                    <Rocket className="w-5 h-5 text-muted-foreground/50" />
                  </div>
                  <h3 className="text-sm font-medium text-foreground mb-1">
                    {debouncedSearch ? 'No results' : 'No Apps yet'}
                  </h3>
                  <p className="text-sm text-muted-foreground text-center mb-5 max-w-xs">
                    {debouncedSearch
                      ? 'No apps match your search.'
                      : 'Ignite a Spark to scaffold it into a full app.'}
                  </p>
                  {debouncedSearch && (
                    <Button variant="outline" size="sm" onClick={() => setSearchQuery('')}>
                      Clear search
                    </Button>
                  )}
                </div>
              ) : (
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-x-5 gap-y-8">
                  {filteredApps.map((app) => (
                    <AppGridCard
                      key={app.id}
                      app={app}
                      isRunning={previewStates[app.id]?.running}
                      onClick={() => handleSelectApp(app.id)}
                    />
                  ))}
                </div>
              )}
            </div>

            {embedded && (hasNext || hasPrevious) && (
              <div className="md:hidden pb-20">
                <PaginationBar page={page} totalPages={totalPages} hasNext={hasNext} hasPrevious={hasPrevious} onPageChange={setPage} isLoading={isLoading} />
              </div>
            )}
          </div>

          {(hasNext || hasPrevious) && (
            <div className={embedded ? "hidden md:block" : ""}>
              <PaginationBar page={page} totalPages={totalPages} hasNext={hasNext} hasPrevious={hasPrevious} onPageChange={setPage} isLoading={isLoading} />
            </div>
          )}
        </>
      )}
    </div>
  )
}

// =============================================================================
// Grid Card
// =============================================================================

function AppGridCard({
  app,
  isRunning,
  onClick,
}: {
  app: AppListItem
  isRunning?: boolean
  onClick: () => void
}) {
  return (
    <div className="group cursor-pointer" onClick={onClick}>
      <div className="relative aspect-[16/10] rounded-xl overflow-hidden bg-muted/40 transition-transform duration-200 ease-out group-hover:-translate-y-1 group-hover:shadow-lg group-hover:shadow-black/10 flex items-center justify-center">
        <div className="flex flex-col items-center gap-2">
          <Rocket className="h-8 w-8 text-orange-500/60" />
          <span className="text-xs text-muted-foreground capitalize">{app.spark_framework}</span>
        </div>
        {isRunning && (
          <div className="absolute top-2 right-2">
            <span className="relative flex h-2.5 w-2.5">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
              <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-emerald-500" />
            </span>
          </div>
        )}
      </div>
      <p className="mt-2.5 text-sm text-foreground truncate">{app.title}</p>
    </div>
  )
}

// =============================================================================
// Detail View
// =============================================================================

function AppDetailView({
  app,
  onBack,
}: {
  app: App
  onBack: () => void
}) {
  const navigate = useNavigate()
  const { toast } = useToast()
  const { user } = useAuthStore()
  const userId = user?.id?.toString()

  const previewState = useAppsStore((s) => s.previewStates[app.id])
  const setPreviewState = useAppsStore((s) => s.setPreviewState)
  const clearPreviewState = useAppsStore((s) => s.clearPreviewState)

  const isRunning = previewState?.running ?? false
  const isLoading = previewState?.loading ?? false
  const port = previewState?.port ?? null

  // Preview states: 'idle' | 'waiting' (health polling) | 'ready' (iframe) | 'failed'
  const [previewStatus, setPreviewStatus] = useState<'idle' | 'waiting' | 'ready' | 'failed'>('idle')
  const [previewToken, setPreviewToken] = useState<string | null>(null)
  const iframeKeyRef = useRef(0)

  // Sync preview status with backend on mount — clears stale Zustand state
  useEffect(() => {
    appsAPI.previewStatus(app.id).then((st) => {
      if (st.running) {
        setPreviewState(app.id, { running: true, port: st.port, loading: false })
      } else {
        clearPreviewState(app.id)
      }
    })
  }, [app.id, setPreviewState, clearPreviewState])

  // When running + port: poll health, then fetch token
  useEffect(() => {
    if (!isRunning || !port || !userId) {
      if (!isRunning) {
        setPreviewStatus('idle')
        setPreviewToken(null)
      }
      return
    }

    let cancelled = false
    let attempts = 0
    const maxAttempts = 30 // 30 seconds max

    setPreviewStatus('waiting')

    const pollHealth = async () => {
      while (!cancelled && attempts < maxAttempts) {
        const ready = await checkProcessHealth(userId, port)
        if (cancelled) return
        if (ready) {
          try {
            const token = await fetchPreviewToken(userId, port)
            if (!cancelled) {
              setPreviewToken(token)
              setPreviewStatus('ready')
              iframeKeyRef.current += 1
            }
          } catch {
            if (!cancelled) setPreviewStatus('failed')
          }
          return
        }
        attempts++
        await new Promise(r => setTimeout(r, 1000))
      }
      if (!cancelled) setPreviewStatus('failed')
    }

    pollHealth()

    // Refresh token every 4 min once ready
    const refreshTimer = setInterval(async () => {
      if (cancelled) return
      try {
        const token = await fetchPreviewToken(userId, port)
        if (!cancelled) setPreviewToken(token)
      } catch {}
    }, 4 * 60 * 1000)

    return () => { cancelled = true; clearInterval(refreshTimer) }
  }, [isRunning, port, userId])

  const handleStart = useCallback(async () => {
    setPreviewState(app.id, { loading: true })
    try {
      const result = await appsAPI.startPreview(app.id)
      setPreviewState(app.id, { running: true, port: result.port, loading: false })
      toast({ title: 'Dev server started' })
    } catch (error: any) {
      setPreviewState(app.id, { loading: false })
      const status = error?.response?.status
      const raw = error?.response?.data?.error || error?.message || 'Unknown error'
      const msg = typeof raw === 'string' ? raw : JSON.stringify(raw)
      if (status === 409) {
        toast({ title: 'Port already in use', description: 'Stop the other preview first', variant: 'destructive' })
      } else if (status === 429) {
        toast({ title: 'Process limit reached', description: 'Maximum 3 concurrent processes — stop one first', variant: 'destructive' })
      } else {
        toast({ title: 'Failed to start preview', description: msg, variant: 'destructive' })
      }
    }
  }, [app.id, setPreviewState, toast])

  const handleStop = useCallback(async () => {
    setPreviewState(app.id, { loading: true })
    try {
      await appsAPI.stopPreview(app.id, previewState?.port ?? undefined)
      toast({ title: 'Dev server stopped' })
    } catch {
      // Process may already be dead (404) — still clean up UI
    } finally {
      clearPreviewState(app.id)
      setPreviewToken(null)
      setPreviewStatus('idle')
    }
  }, [app.id, previewState?.port, setPreviewState, clearPreviewState, toast])

  const handleRefreshPreview = useCallback(() => {
    iframeKeyRef.current += 1
    // Force re-render by toggling status
    setPreviewStatus('waiting')
    if (userId && port) {
      fetchPreviewToken(userId, port)
        .then(token => { setPreviewToken(token); setPreviewStatus('ready') })
        .catch(() => setPreviewStatus('failed'))
    }
  }, [userId, port])

  const formattedDate = new Date(app.created_at).toLocaleDateString('en-US', {
    month: 'long', day: 'numeric', year: 'numeric',
  })

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="max-w-6xl mx-auto px-4 sm:px-6 pt-8 pb-20">
        <button
          onClick={onBack}
          className="group/back inline-flex items-center gap-2 text-[13px] text-muted-foreground hover:text-foreground transition-colors mb-8"
        >
          <ArrowLeft className="h-3.5 w-3.5 transition-transform group-hover/back:-translate-x-0.5" />
          Back
        </button>

        <div className="mb-8">
          <div className="mb-3">
            <span className="text-[10px] uppercase tracking-wider font-medium px-1.5 py-0.5 rounded bg-orange-500/10 text-orange-500">
              App
            </span>
          </div>

          <div className="flex items-start justify-between gap-6">
            <div className="min-w-0 flex-1">
              <h1 className="text-[22px] font-semibold tracking-tight text-foreground leading-tight">
                {app.title}
              </h1>
              <p className="text-[13px] text-muted-foreground/70 mt-1.5">
                {formattedDate}
                {app.version > 1 && <span className="ml-2 text-muted-foreground/50">v{app.version}</span>}
              </p>
            </div>

            <div className="flex items-center gap-1.5 shrink-0">
              <Button
                variant={isRunning ? 'destructive' : 'default'}
                size="sm"
                className="h-8 px-3"
                onClick={isRunning ? handleStop : handleStart}
                disabled={isLoading}
              >
                {isLoading ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin mr-1.5" />
                ) : isRunning ? (
                  <Square className="h-3.5 w-3.5 mr-1.5" />
                ) : (
                  <Play className="h-3.5 w-3.5 mr-1.5" />
                )}
                {isRunning ? 'Stop' : 'Run Preview'}
              </Button>
            </div>
          </div>
        </div>

        {/* Preview card — shown when process is running */}
        {isRunning && (
          <div className="mb-8 rounded-xl border border-border/40 overflow-hidden">
            {/* Preview toolbar */}
            <div className="flex items-center justify-between px-4 py-2 bg-muted/30 border-b border-border/30">
              <div className="flex items-center gap-2">
                <span className="relative flex h-2 w-2">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
                  <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500" />
                </span>
                <Globe className="h-3.5 w-3.5 text-muted-foreground" />
                <span className="font-mono text-xs text-muted-foreground">localhost:{port}</span>
              </div>
              {previewStatus === 'ready' && (
                <Button variant="ghost" size="sm" className="h-6 px-2 text-[11px]" onClick={handleRefreshPreview}>
                  <RefreshCw className="h-3 w-3" />
                </Button>
              )}
            </div>

            {/* Preview content */}
            <div className="bg-white" style={{ height: 500 }}>
              {previewStatus === 'waiting' && (
                <div className="flex flex-col items-center justify-center h-full gap-3">
                  <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
                  <p className="text-sm text-muted-foreground">Starting dev server...</p>
                  <p className="text-xs text-muted-foreground/60">Waiting for port {port} to be ready</p>
                </div>
              )}
              {previewStatus === 'failed' && (
                <div className="flex flex-col items-center justify-center h-full gap-3">
                  <div className="w-10 h-10 rounded-full bg-red-500/10 flex items-center justify-center">
                    <X className="w-5 h-5 text-red-500" />
                  </div>
                  <p className="text-sm text-foreground font-medium">Dev server failed to start</p>
                  <p className="text-xs text-muted-foreground text-center max-w-sm">
                    The process was started but never began listening on port {port}.
                    The project may need to be re-ignited to restore dependencies.
                  </p>
                  <Button variant="outline" size="sm" className="mt-2" onClick={handleStart}>
                    Retry
                  </Button>
                </div>
              )}
              {previewStatus === 'ready' && previewToken && userId && port && (
                <iframe
                  key={iframeKeyRef.current}
                  src={getPreviewUrl(userId, port, previewToken)}
                  className="w-full h-full border-0"
                  sandbox="allow-scripts allow-same-origin allow-forms allow-popups"
                  title={`Preview ${app.title}`}
                />
              )}
            </div>
          </div>
        )}

        {/* About card */}
        <div className="grid grid-cols-1 sm:grid-cols-[1fr_auto] gap-8 items-start">
          <div>
            <h2 className="text-[13px] font-medium text-foreground/80 uppercase tracking-wider mb-3">About</h2>
            <div className="rounded-xl bg-muted/20 border border-border/30 divide-y divide-border/20">
              {[
                ['Framework', <span key="fw" className="capitalize">{app.spark_framework}</span>],
                ['Command', <code key="cmd" className="text-xs">{app.preview_command}</code>],
                ['Version', app.version],
                ['Created', formattedDate],
                ['Source Spark', app.spark_title],
              ].map(([label, value], i) => (
                <div key={i} className="flex items-center justify-between px-4 py-2.5 text-[13px]">
                  <span className="text-muted-foreground/70">{label as string}</span>
                  <span className="text-foreground/90 truncate ml-6 max-w-[220px]">{value as React.ReactNode}</span>
                </div>
              ))}
            </div>
          </div>

          <div className="flex flex-col gap-3 sm:pt-8">
            {app.conversation_id && (
              <button
                onClick={() => navigate({ to: '/chats', search: { conversation: app.conversation_id! } })}
                className="inline-flex items-center gap-2 h-9 px-4 rounded-full text-[13px] font-medium text-foreground border border-border/50 hover:bg-muted/40 hover:border-border transition-all"
              >
                View full chat
                <ExternalLink className="h-3.5 w-3.5 text-muted-foreground" />
              </button>
            )}
            {app.latest_deployment?.preview_url && (
              <a
                href={app.latest_deployment.preview_url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-2 h-9 px-4 rounded-full text-[13px] font-medium text-foreground border border-border/50 hover:bg-muted/40 hover:border-border transition-all"
              >
                View deployment
                <ExternalLink className="h-3.5 w-3.5 text-muted-foreground" />
              </a>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

// =============================================================================
// Pagination
// =============================================================================

function PaginationBar({
  page,
  totalPages,
  hasNext,
  hasPrevious,
  onPageChange,
  isLoading,
}: {
  page: number
  totalPages: number
  hasNext: boolean
  hasPrevious: boolean
  onPageChange: (p: number) => void
  isLoading: boolean
}) {
  return (
    <div className="shrink-0 flex items-center justify-center gap-2 py-3 border-t border-border/30 bg-background">
      <Button variant="ghost" size="sm" onClick={() => onPageChange(page - 1)} disabled={!hasPrevious || isLoading} className="h-8 px-3">
        <ChevronLeft className="h-4 w-4 mr-1" />
        Prev
      </Button>
      <div className="flex items-center gap-1 px-2">
        {Array.from({ length: Math.min(totalPages, 5) }).map((_, i) => {
          let pageNum: number
          if (totalPages <= 5) pageNum = i + 1
          else if (page <= 3) pageNum = i + 1
          else if (page >= totalPages - 2) pageNum = totalPages - 4 + i
          else pageNum = page - 2 + i
          return (
            <button
              key={pageNum}
              onClick={() => onPageChange(pageNum)}
              disabled={isLoading}
              className={cn(
                'w-8 h-8 rounded-md text-sm font-medium transition-colors',
                page === pageNum ? 'bg-foreground text-background' : 'text-muted-foreground hover:text-foreground hover:bg-muted/60'
              )}
            >
              {pageNum}
            </button>
          )
        })}
      </div>
      <Button variant="ghost" size="sm" onClick={() => onPageChange(page + 1)} disabled={!hasNext || isLoading} className="h-8 px-3">
        Next
        <ChevronRight className="h-4 w-4 ml-1" />
      </Button>
    </div>
  )
}
