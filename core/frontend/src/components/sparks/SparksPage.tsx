import { useState, useEffect, useCallback, useMemo } from 'react'
import { useNavigate } from '@tanstack/react-router'
import {
  ArrowLeft,
  ChevronLeft,
  ChevronRight,
  Copy,
  Check,
  Download,
  ExternalLink,
  Maximize2,
  MoreHorizontal,
  Search,
  Trash2,
  X,
  Plus,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { TypeBadge } from '@/lib/type-badges'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { useUIStore } from '@/store/uiStore'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { sparksAPI, type Spark, type SparkVersion } from '@/api/sparks'
import { SparkRenderer } from '@/components/models/SparkRenderer'
import { SparkFullscreenOverlay } from '@/components/models/SparkFullscreenDialog'
import { useNavigationStore } from '@/store/navigationStore'
import { useToast } from '@/hooks/use-toast'
import { PremiumMenuIcon } from '@/components/ui/premium-menu-icon'
import { IgniteButton } from '@/components/sparks/IgniteButton'

const PAGE_SIZE = 12

const FRAMEWORK_FILTERS = [
  { value: 'all', label: 'All' },
  { value: 'react,html', label: 'Interactive' },
  { value: 'svg,mermaid', label: 'Visual' },
  { value: 'markdown,csv,ics,pdf,docx,xlsx', label: 'Documents' },
] as const

export function SparksPage({ embedded }: { embedded?: boolean }) {
  const navigate = useNavigate()
  const { openMobileSidebar } = useNavigationStore()
  const { toast } = useToast()
  const isMobile = useUIStore((state) => state.isMobile)

  const [sparks, setSparks] = useState<Spark[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [page, setPage] = useState(1)
  const [totalCount, setTotalCount] = useState(0)
  const [hasNext, setHasNext] = useState(false)
  const [hasPrevious, setHasPrevious] = useState(false)

  const [activeFilter, setActiveFilter] = useState('all')
  const [searchQuery, setSearchQuery] = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')

  // Track all known frameworks (fetched once without filter to populate pills)

  const [selectedSpark, setSelectedSpark] = useState<Spark | null>(null)
  const [sparkToDelete, setSparkToDelete] = useState<Spark | null>(null)
  const [versions, setVersions] = useState<SparkVersion[]>([])

  // Debounce search
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearch(searchQuery)
      setPage(1)
    }, 300)
    return () => clearTimeout(timer)
  }, [searchQuery])

  // Load sparks — server-side framework filter
  const loadSparks = useCallback(async () => {
    setIsLoading(true)
    try {
      const response = await sparksAPI.list({
        page,
        page_size: PAGE_SIZE,
        ordering: '-created_at',
        ...(debouncedSearch && { search: debouncedSearch }),
        ...(activeFilter !== 'all' && { framework: activeFilter }),
      })
      setSparks(response.results)
      setTotalCount(response.count)
      setHasNext(response.next !== null)
      setHasPrevious(response.previous !== null)

    } catch {
      toast({
        title: 'Failed to load Sparks',
        description: 'Could not fetch your Sparks. Please try again.',
        variant: 'destructive',
      })
    } finally {
      setIsLoading(false)
    }
  }, [page, debouncedSearch, activeFilter, toast])

  useEffect(() => {
    loadSparks()
  }, [loadSparks])

  // Reset page when filter changes
  const handleFilterChange = useCallback((value: string) => {
    setActiveFilter(value)
    setPage(1)
  }, [])

  const visibleFilters = FRAMEWORK_FILTERS

  // Fetch versions when a spark is selected
  useEffect(() => {
    if (!selectedSpark) {
      setVersions([])
      return
    }
    let cancelled = false
    sparksAPI.getVersions(selectedSpark.id).then((v) => {
      if (!cancelled) setVersions(v)
    })
    return () => { cancelled = true }
  }, [selectedSpark?.id])

  const handleNavigateToVersion = useCallback(async (sparkId: string) => {
    const spark = await sparksAPI.get(sparkId)
    if (spark) setSelectedSpark(spark)
  }, [])

  const handleDelete = useCallback(async () => {
    if (!sparkToDelete) return
    try {
      await sparksAPI.delete(sparkToDelete.id)
      toast({ title: 'Spark deleted', description: 'The Spark has been removed.' })
      setSparkToDelete(null)
      loadSparks()
    } catch {
      toast({
        title: 'Failed to delete',
        description: 'Could not delete the Spark. Please try again.',
        variant: 'destructive',
      })
    }
  }, [sparkToDelete, toast, loadSparks])

  const totalPages = Math.ceil(totalCount / PAGE_SIZE)

  return (
    <div className="h-full flex flex-col overflow-hidden bg-background">
      {/* Inline detail view — replaces gallery */}
      {selectedSpark ? (
        <SparkDetailView
          spark={selectedSpark}
          versions={versions}
          onBack={() => setSelectedSpark(null)}
          onNavigateVersion={handleNavigateToVersion}
          onDelete={() => {
            setSparkToDelete(selectedSpark)
            setSelectedSpark(null)
          }}
        />
      ) : (
      <>
      {/* Mobile header */}
      {!embedded && (
      <div className="md:hidden flex items-center justify-between px-4 py-3 border-b border-border/50 sticky top-0 z-40 bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
        <button
          onClick={openMobileSidebar}
          className="p-2 -ml-2 text-foreground transition-colors"
        >
          <PremiumMenuIcon size={18} />
        </button>
        <h1 className="text-base font-medium text-foreground">Sparks</h1>
        <div className="w-8" />
      </div>
      )}

      {/* Scrollable content */}
      <div className="flex-1 overflow-y-auto">
        {/* Sticky desktop header */}
        <div className="sticky top-0 z-30 bg-background hidden md:block">
          <div className={cn("max-w-6xl mx-auto px-4 sm:px-6 pb-5", embedded ? "pt-4" : "pt-8")}>
            {/* Title row */}
            {!embedded && (
            <div className="flex items-center justify-between gap-4">
              <h1 className="text-2xl font-semibold tracking-tight text-foreground">
                Sparks
              </h1>
              <button
                onClick={() => navigate({ to: '/chats' })}
                className="inline-flex items-center gap-1.5 h-9 px-4 rounded-full text-sm font-medium text-brand-700 dark:text-brand-400 border border-brand-300 dark:border-brand-700 hover:bg-brand-50 dark:hover:bg-brand-950/40 transition-colors shrink-0"
              >
                <Plus className="h-4 w-4" />
                New spark
              </button>
            </div>
            )}

            {/* Filters */}
            <div className={cn("flex items-center gap-3", !embedded && "mt-5")}>
              {visibleFilters.length > 1 && (
                <div className="flex items-center gap-2 overflow-x-auto scrollbar-none">
                  {visibleFilters.map((filter) => (
                    <button
                      key={filter.value}
                      onClick={() => handleFilterChange(filter.value)}
                      className={cn(
                        'px-3.5 py-1.5 rounded-full text-sm whitespace-nowrap transition-colors',
                        activeFilter === filter.value
                          ? 'bg-foreground text-background'
                          : 'text-muted-foreground hover:text-foreground hover:bg-muted/50'
                      )}
                    >
                      {filter.label}
                    </button>
                  ))}
                </div>
              )}

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
                  <button
                    onClick={() => setSearchQuery('')}
                    className="absolute right-2.5 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                  >
                    <X className="h-3.5 w-3.5" />
                  </button>
                )}
              </div>
            </div>
          </div>
        </div>

        {/* Mobile search + filters — sticky below mobile header */}
        <div className="md:hidden px-4 py-3 space-y-2.5 border-b border-border/30 sticky top-0 z-20 bg-background">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground pointer-events-none" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search sparks..."
              className="w-full h-9 pl-9 pr-9 rounded-lg bg-muted/50 border border-border/50 text-sm placeholder:text-muted-foreground/60 focus:outline-none focus:ring-1 focus:ring-ring focus:border-ring transition-colors"
              maxLength={200}
            />
            {searchQuery && (
              <button
                onClick={() => setSearchQuery('')}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            )}
          </div>
          {visibleFilters.length > 1 && (
            <div className="flex items-center gap-1.5 overflow-x-auto scrollbar-none pb-0.5">
              {visibleFilters.map((filter) => (
                <button
                  key={filter.value}
                  onClick={() => handleFilterChange(filter.value)}
                  className={cn(
                    'px-3 py-1.5 rounded-full text-xs font-medium whitespace-nowrap transition-colors border',
                    activeFilter === filter.value
                      ? 'bg-foreground text-background border-foreground'
                      : 'bg-transparent text-muted-foreground border-border/60 hover:text-foreground hover:border-border'
                  )}
                >
                  {filter.label}
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Grid content */}
        <div className="max-w-6xl mx-auto px-4 sm:px-6 py-6 pb-24 md:pb-10">
          {isLoading && sparks.length === 0 ? (
            <SkeletonGrid />
          ) : sparks.length === 0 && (debouncedSearch || activeFilter !== 'all') ? (
            <EmptySearch
              hasSearch={!!debouncedSearch}
              onClear={() => {
                setSearchQuery('')
                handleFilterChange('all')
              }}
            />
          ) : sparks.length === 0 ? (
            <EmptyState onCreateClick={() => navigate({ to: '/chats' })} />
          ) : (
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-x-5 gap-y-8">
                {sparks.map((spark) => (
                  <SparkCard
                    key={spark.id}
                    spark={spark}
                    onClick={() => setSelectedSpark(spark)}
                    onDelete={() => setSparkToDelete(spark)}
                  />
                ))}
              </div>
          )}
        </div>

        {/* Pagination inside scroll area on mobile when embedded (bottom tab bar covers pinned footer) */}
        {embedded && (hasNext || hasPrevious) && (
          <div className="md:hidden pb-20">
            <PaginationBar
              page={page}
              totalPages={totalPages}
              hasNext={hasNext}
              hasPrevious={hasPrevious}
              onPageChange={setPage}
              isLoading={isLoading}
            />
          </div>
        )}
      </div>

      {/* Pagination pinned to bottom — always when standalone, desktop-only when embedded */}
      {(hasNext || hasPrevious) && (
        <div className={embedded ? "hidden md:block" : ""}>
          <PaginationBar
            page={page}
            totalPages={totalPages}
            hasNext={hasNext}
            hasPrevious={hasPrevious}
            onPageChange={setPage}
            isLoading={isLoading}
          />
        </div>
      )}
      </>
      )}

      {/* Delete confirmation */}
      <AlertDialog open={sparkToDelete !== null} onOpenChange={() => setSparkToDelete(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete Spark?</AlertDialogTitle>
            <AlertDialogDescription>
              This will permanently delete "{sparkToDelete?.title}". This action cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDelete}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}

// =============================================================================
// Spark Card
// =============================================================================

function SparkCard({
  spark,
  onClick,
  onDelete,
}: {
  spark: Spark
  onClick: () => void
  onDelete: () => void
}) {
  return (
    <div
      className="group cursor-pointer"
      onClick={onClick}
    >
      {/* Preview thumbnail */}
      <div className="relative aspect-[16/10] rounded-xl overflow-hidden bg-muted/40 transition-transform duration-200 ease-out group-hover:-translate-y-1 group-hover:shadow-lg group-hover:shadow-black/10">
        <SparkRenderer
          code={spark.code}
          assets={spark.assets}
          framework={spark.framework}
          title={spark.title}
          downloadUrl={spark.download_url}
          hideHeader
          compact
          className="h-full w-full"
        />

        {/* Delete on hover */}
        <div className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 transition-opacity duration-150">
          <button
            type="button"
            className="inline-flex items-center justify-center h-7 w-7 rounded-lg bg-black/50 backdrop-blur-sm hover:bg-red-600 text-white/80 hover:text-white transition-colors"
            onClick={(e) => {
              e.stopPropagation()
              onDelete()
            }}
          >
            <Trash2 className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>

      {/* Title below preview */}
      <p className="mt-2.5 text-sm text-foreground truncate">
        {spark.title}
      </p>
    </div>
  )
}

// =============================================================================
// Detail View (replaces modal)
// =============================================================================

function SparkDetailView({
  spark,
  versions,
  onBack,
  onNavigateVersion,
  onDelete,
}: {
  spark: Spark
  versions: SparkVersion[]
  onBack: () => void
  onNavigateVersion: (sparkId: string) => void
  onDelete: () => void
}) {
  const navigate = useNavigate()
  const { toast } = useToast()
  const [copied, setCopied] = useState(false)
  const [isFullscreen, setIsFullscreen] = useState(false)

  const currentVersionIndex = versions.findIndex((v) => v.id === spark.id)
  const hasPrevVersion = currentVersionIndex < versions.length - 1
  const hasNextVersion = currentVersionIndex > 0

  const handleCopy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(spark.code)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
      toast({ title: 'Copied to clipboard' })
    } catch {
      toast({ title: 'Failed to copy', variant: 'destructive' })
    }
  }, [spark.code, toast])

  const handleDownload = useCallback(() => {
    if (spark.download_url) {
      const token = localStorage.getItem('access_token')
      fetch(spark.download_url, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      })
        .then((r) => r.blob())
        .then((blob) => {
          const ext: Record<string, string> = { csv: 'csv', ics: 'ics', pdf: 'pdf', docx: 'docx', xlsx: 'xlsx' }
          const filename = `${spark.title.toLowerCase().replace(/\s+/g, '-')}.${ext[spark.framework] || 'bin'}`
          const url = URL.createObjectURL(blob)
          const a = document.createElement('a')
          a.href = url
          a.download = filename
          a.click()
          URL.revokeObjectURL(url)
        })
      return
    }
    const ext: Record<string, string> = {
      react: 'tsx', html: 'html', svg: 'svg', markdown: 'md', mermaid: 'mmd',
      csv: 'csv', ics: 'ics', pdf: 'py', docx: 'py', xlsx: 'py',
    }
    const filename = `${spark.title.toLowerCase().replace(/\s+/g, '-')}.${ext[spark.framework] || 'txt'}`
    const blob = new Blob([spark.code], { type: 'text/plain' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    a.click()
    URL.revokeObjectURL(url)
  }, [spark])

  const formattedDate = new Date(spark.created_at).toLocaleDateString('en-US', {
    month: 'long',
    day: 'numeric',
    year: 'numeric',
  })

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="max-w-6xl mx-auto px-4 sm:px-6 pt-8 pb-20">

        {/* Back navigation */}
        <button
          onClick={onBack}
          className="group/back inline-flex items-center gap-2 text-[13px] text-muted-foreground hover:text-foreground transition-colors mb-8"
        >
          <ArrowLeft className="h-3.5 w-3.5 transition-transform group-hover/back:-translate-x-0.5" />
          Back
        </button>

        {/* Header area */}
        <div className="mb-8">
          {/* Framework pill */}
          <div className="mb-3">
            <TypeBadge type={spark.framework} />
          </div>

          {/* Title + actions row */}
          <div className="flex items-start justify-between gap-6">
            <div className="min-w-0 flex-1">
              <h1 className="text-[22px] font-semibold tracking-tight text-foreground leading-tight">
                {spark.title}
              </h1>
              <p className="text-[13px] text-muted-foreground/70 mt-1.5">
                {formattedDate}
                {spark.version > 1 && (
                  <span className="ml-2 text-muted-foreground/50">v{spark.version}</span>
                )}
              </p>
            </div>

            {/* Action toolbar */}
            <div className="flex items-center gap-1.5 shrink-0 -mt-0.5">
              {versions.length > 1 && (
                <div className="flex items-center mr-1 rounded-lg border border-border/40 overflow-hidden">
                  <button
                    className="p-1.5 hover:bg-muted/80 transition-colors disabled:opacity-25"
                    onClick={() => hasPrevVersion && onNavigateVersion(versions[currentVersionIndex + 1].id)}
                    disabled={!hasPrevVersion}
                  >
                    <ChevronLeft className="h-3.5 w-3.5" />
                  </button>
                  <span className="text-[11px] text-muted-foreground tabular-nums px-1 border-x border-border/40 py-1.5">
                    v{spark.version}
                  </span>
                  <button
                    className="p-1.5 hover:bg-muted/80 transition-colors disabled:opacity-25"
                    onClick={() => hasNextVersion && onNavigateVersion(versions[currentVersionIndex - 1].id)}
                    disabled={!hasNextVersion}
                  >
                    <ChevronRight className="h-3.5 w-3.5" />
                  </button>
                </div>
              )}

              <IgniteButton sparkId={spark.id} sparkTitle={spark.title} framework={spark.framework} latestDeployment={spark.latest_deployment} conversationId={spark.conversation_id} isIgnited={spark.is_ignited} variant="full" />

              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <button className="inline-flex items-center justify-center h-8 w-8 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted/50 transition-all">
                    <MoreHorizontal className="h-4 w-4" />
                  </button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end">
                  <DropdownMenuItem onClick={handleCopy}>
                    {copied ? <Check className="h-4 w-4 mr-2 text-emerald-400" /> : <Copy className="h-4 w-4 mr-2" />}
                    {copied ? 'Copied' : 'Copy code'}
                  </DropdownMenuItem>
                  <DropdownMenuItem onClick={handleDownload}>
                    <Download className="h-4 w-4 mr-2" />
                    Download
                  </DropdownMenuItem>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem onClick={onDelete} className="text-destructive focus:text-destructive">
                    <Trash2 className="h-4 w-4 mr-2" />
                    Delete
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </div>
          </div>
        </div>

        {/* Preview container — the hero */}
        <div className="relative group/preview">
          {/* Subtle ambient glow behind the preview */}
          <div className="absolute -inset-px rounded-2xl bg-gradient-to-b from-border/50 via-border/20 to-border/50 opacity-0 group-hover/preview:opacity-100 transition-opacity duration-500" />
          <div className="relative rounded-2xl overflow-hidden ring-1 ring-border/30">
            <SparkRenderer
              code={spark.code}
              assets={spark.assets}
              framework={spark.framework}
              title={spark.title}
              downloadUrl={spark.download_url}
              hideHeader
              className="w-full aspect-[4/3]"
            />

            {/* Fullscreen button */}
            <div className="absolute top-3 right-3 opacity-0 group-hover/preview:opacity-100 transition-opacity duration-200">
              <TooltipProvider delayDuration={200}>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <button
                      onClick={() => setIsFullscreen(true)}
                      className="inline-flex items-center justify-center h-8 w-8 rounded-lg bg-black/50 backdrop-blur-sm text-white/80 hover:text-white hover:bg-black/70 transition-all"
                    >
                      <Maximize2 className="h-4 w-4" />
                    </button>
                  </TooltipTrigger>
                  <TooltipContent side="bottom">Fullscreen</TooltipContent>
                </Tooltip>
              </TooltipProvider>
            </div>
          </div>
        </div>

        <SparkFullscreenOverlay
          spark={spark}
          open={isFullscreen}
          onClose={() => setIsFullscreen(false)}
        />

        {/* Bottom metadata — two-column layout */}
        <div className="mt-10 grid grid-cols-1 sm:grid-cols-[1fr_auto] gap-8 items-start">

          {/* About card */}
          <div>
            <h2 className="text-[13px] font-medium text-foreground/80 uppercase tracking-wider mb-3">
              About
            </h2>
            <div className="rounded-xl bg-muted/20 border border-border/30 divide-y divide-border/20">
              {[
                ['Type', <span key="type" className="capitalize">{spark.framework}</span>],
                ['Version', spark.version],
                ['Created', formattedDate],
                ...(spark.chat_name ? [['Chat', spark.chat_name]] : []),
              ].map(([label, value], i) => (
                <div key={i} className="flex items-center justify-between px-4 py-2.5 text-[13px]">
                  <span className="text-muted-foreground/70">{label as string}</span>
                  <span className="text-foreground/90 truncate ml-6 max-w-[220px]">
                    {value as React.ReactNode}
                  </span>
                </div>
              ))}
            </div>
          </div>

          {/* Source link */}
          {spark.conversation_id && (
            <div className="sm:pt-8">
              <button
                onClick={() => navigate({ to: '/chats', search: { conversation: spark.conversation_id! } })}
                className="inline-flex items-center gap-2 h-9 px-4 rounded-full text-[13px] font-medium text-foreground border border-border/50 hover:bg-muted/40 hover:border-border transition-all"
              >
                View full chat
                <ExternalLink className="h-3.5 w-3.5 text-muted-foreground" />
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

// =============================================================================
// Skeleton Loading
// =============================================================================

function SkeletonGrid() {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-x-5 gap-y-8">
      {Array.from({ length: 12 }).map((_, i) => (
        <div key={i}>
          <Skeleton className="aspect-[16/10] rounded-xl" />
          <Skeleton className="h-4 w-2/3 mt-2.5" />
        </div>
      ))}
    </div>
  )
}

// =============================================================================
// Empty States
// =============================================================================

function EmptySearch({
  hasSearch,
  onClear,
}: {
  hasSearch: boolean
  onClear: () => void
}) {
  return (
    <div className="flex flex-col items-center justify-center py-20 px-6">
      <div className="w-12 h-12 rounded-full bg-muted/60 flex items-center justify-center mb-4">
        <Search className="w-5 h-5 text-muted-foreground/50" />
      </div>
      <h3 className="text-sm font-medium text-foreground mb-1">No results</h3>
      <p className="text-sm text-muted-foreground text-center mb-5 max-w-xs">
        {hasSearch
          ? 'No sparks match your search. Try different keywords.'
          : 'No sparks match this filter.'}
      </p>
      <Button variant="outline" size="sm" onClick={onClear}>
        Clear filters
      </Button>
    </div>
  )
}

function EmptyState({ onCreateClick }: { onCreateClick: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center py-20 px-6">
      <div className="w-12 h-12 rounded-full bg-muted/60 flex items-center justify-center mb-4">
        <Plus className="w-5 h-5 text-muted-foreground/50" />
      </div>
      <h3 className="text-sm font-medium text-foreground mb-1">No Sparks yet</h3>
      <p className="text-sm text-muted-foreground text-center mb-5 max-w-xs">
        Ask the AI to create an interactive component and it will show up here.
      </p>
      <button
        onClick={onCreateClick}
        className="inline-flex items-center gap-1.5 h-9 px-4 rounded-full text-sm font-medium text-brand-700 dark:text-brand-400 border border-brand-300 dark:border-brand-700 hover:bg-brand-50 dark:hover:bg-brand-950/40 transition-colors"
      >
        <Plus className="h-4 w-4" />
        Create Your First Spark
      </button>
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
      <Button
        variant="ghost"
        size="sm"
        onClick={() => onPageChange(page - 1)}
        disabled={!hasPrevious || isLoading}
        className="h-8 px-3"
      >
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
                page === pageNum
                  ? 'bg-foreground text-background'
                  : 'text-muted-foreground hover:text-foreground hover:bg-muted/60'
              )}
            >
              {pageNum}
            </button>
          )
        })}
      </div>

      <Button
        variant="ghost"
        size="sm"
        onClick={() => onPageChange(page + 1)}
        disabled={!hasNext || isLoading}
        className="h-8 px-3"
      >
        Next
        <ChevronRight className="h-4 w-4 ml-1" />
      </Button>
    </div>
  )
}

export default SparksPage
