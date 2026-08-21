/**
 * CreationsSidePanel Component
 *
 * A unified side panel for displaying Sparks, Images, and Videos from the current chat.
 * Clicking a spark fills the entire panel with Preview/Code tabs in the header.
 */

import { useState, useCallback, useMemo, useRef, useEffect, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import {
  Code2,
  Copy,
  Check,
  Eye,
  RefreshCw,
  X,
  ArrowLeft,
  FileCode2,
  GripVertical,
  ChevronLeft,
  ChevronRight,
  Image as ImageIcon,
  Film,
  Play,
  Zap,
  Download,
  MoreHorizontal,
  Rocket,
  Loader2,
} from 'lucide-react'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { cn } from '@/lib/utils'
import { TypeBadge } from '@/lib/type-badges'
import { useSettingsStore } from '@/store/settingsStore'
import { getCodeTheme } from '@/constants/codeThemes'
import { useArtifactsPanelStore, type ArtifactSection } from '@/store/artifactsPanelStore'
import type { SparkDefinition } from '@/store/sparksStore'
import { SparkRenderer } from './SparkRenderer'
import { SparkFullscreenOverlay } from './SparkFullscreenDialog'
import { type SparkFixRequest } from './SparkAutoFixContext'
import { Button } from '@/components/ui/button'
import { ScrollArea } from '@/components/ui/scroll-area'
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import { useToast } from '@/hooks/use-toast'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { useUIStore } from '@/store/uiStore'
import { sparksAPI, type SparkVersion } from '@/api/sparks'
import { assetsAPI, type Asset, type GalleryAsset } from '@/api/assets'
import { AssetImage } from './AssetImage'
import { VideoThumbnail } from '@/components/videos/VideoPlayer'
import { ImageDetailModal } from '@/components/images/ImageDetailModal'
import { VideoDetailModal } from '@/components/videos/VideoDetailModal'
import { ModelIcon } from './ModelIcon'
import { removeProviderPrefix } from '@/lib/model-utils'
import { useIgniteDeploy, IgniteMenuItems, IgniteDialogs } from '@/components/sparks/IgniteButton'
import { appsAPI, type AppListItem } from '@/api/apps'
import { useAppsStore } from '@/store/appsStore'

/** Chat data with sparks for multi-chat mode */
export interface ChatWithSparks {
  id: string
  model: {
    name: string
    model_id: string
    provider: string
    model_icon_slug?: string
    model_icon_url?: string
    provider_icon_slug?: string
    provider_icon_url?: string
  } | null
  sparks: SparkDefinition[]
}

interface ArtifactsSidePanelProps {
  chatId: string
  conversationId?: string
  sparks: SparkDefinition[]
  chats?: ChatWithSparks[]
  className?: string
  sendSparkFixRequest?: (content: string, sparkFixRequest: SparkFixRequest) => Promise<void>
  sparksEnabled?: boolean
  isLoading?: boolean
  onIgnite?: (sparkId: string, sparkTitle: string) => void
}

// ============================================================================
// Code language map
// ============================================================================

const codeLanguageMap: Record<string, string> = {
  react: 'tsx', html: 'html', svg: 'xml',
  markdown: 'markdown', mermaid: 'mermaid', csv: 'csv', ics: 'text',
  pdf: 'python', docx: 'python', xlsx: 'python',
}

// ============================================================================
// Spark Card (list item)
// ============================================================================

function SparkCard({ spark, onClick }: { spark: SparkDefinition; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className={cn(
        'w-full text-left p-3 rounded-xl border transition-all group',
        'hover:bg-accent/30 hover:border-border/60',
        'bg-card/50 border-border/40'
      )}
    >
      <div className="flex items-center gap-3">
        <div className="flex-1 min-w-0">
          <div className="font-medium text-sm truncate">{spark.title}</div>
          <div className="flex items-center gap-2 mt-1.5">
            <TypeBadge type={spark.framework} />
            {spark.version && spark.version > 1 && (
              <span className="text-xs text-muted-foreground">v{spark.version}</span>
            )}
          </div>
        </div>
      </div>
    </button>
  )
}

// ============================================================================
// Spark Panel Detail — fills entire side panel with tabs in header
// ============================================================================

function SparkPanelDetail({
  spark,
  onBack,
  onNavigateToVersion,
  sendSparkFixRequest,
  sparksEnabled = false,
  onIgnite,
}: {
  spark: SparkDefinition
  onBack: () => void
  onNavigateToVersion: (sparkId: string) => void
  sendSparkFixRequest?: (content: string, sparkFixRequest: SparkFixRequest) => Promise<void>
  sparksEnabled?: boolean
  onIgnite?: (sparkId: string, sparkTitle: string) => void
}) {
  const [activeTab, setActiveTab] = useState<'preview' | 'code'>('preview')
  const [copied, setCopied] = useState(false)
  const [lastError, setLastError] = useState<string | null>(null)
  const [isFixing, setIsFixing] = useState(false)
  const lastErrorRef = useRef<string | null>(null)
  const codeThemeId = useSettingsStore((state) => state.codeTheme)
  const codeTheme = getCodeTheme(codeThemeId)
  const [renderKey, setRenderKey] = useState(0)
  const [versions, setVersions] = useState<SparkVersion[]>([])
  const { toast } = useToast()
  const ignite = useIgniteDeploy({
    sparkId: spark.id,
    sparkTitle: spark.title,
    framework: spark.framework,
    latestDeployment: spark.latest_deployment,
    isIgnited: spark.is_ignited,
    onIgnite,
  })

  // Fetch versions
  useEffect(() => {
    sparksAPI.getVersions(spark.id)
      .then(setVersions)
      .catch(() => setVersions([]))
  }, [spark.id])

  // Clear error when spark code changes
  useEffect(() => {
    setLastError(null)
    lastErrorRef.current = null
    setIsFixing(false)
  }, [spark.code])

  const currentVersionIndex = versions.findIndex((v) => v.id === spark.id)
  const hasPreviousVersion = currentVersionIndex < versions.length - 1
  const hasNextVersion = currentVersionIndex > 0

  const handlePreviousVersion = useCallback(() => {
    if (hasPreviousVersion) {
      onNavigateToVersion(versions[currentVersionIndex + 1].id)
    }
  }, [versions, currentVersionIndex, hasPreviousVersion, onNavigateToVersion])

  const handleNextVersion = useCallback(() => {
    if (hasNextVersion) {
      onNavigateToVersion(versions[currentVersionIndex - 1].id)
    }
  }, [versions, currentVersionIndex, hasNextVersion, onNavigateToVersion])

  const handleSparkError = useCallback((error: string) => {
    if (lastErrorRef.current !== error) {
      lastErrorRef.current = error
      setLastError(error)
    }
  }, [])

  const handleAskAIToFix = useCallback(() => {
    if (!sendSparkFixRequest || !lastError || isFixing) return
    setIsFixing(true)
    sendSparkFixRequest(`Please fix the "${spark.title}" spark component.`, {
      spark_id: spark.id,
      spark_title: spark.title,
      error: lastError,
    })
      .catch(err => console.error('[SparkFix] Failed:', err))
      .finally(() => setTimeout(() => setIsFixing(false), 1000))
  }, [sendSparkFixRequest, lastError, isFixing, spark.id, spark.title])

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

  const handleRefresh = useCallback(() => {
    setRenderKey((k) => k + 1)
    setLastError(null)
    lastErrorRef.current = null
  }, [])

  const handleDownload = useCallback(async () => {
    if (spark.download_url) {
      try {
        const token = localStorage.getItem('access_token')
        const resp = await fetch(spark.download_url, {
          headers: token ? { Authorization: `Bearer ${token}` } : {},
        })
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
        const blob = await resp.blob()
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = spark.title || 'download'
        a.click()
        URL.revokeObjectURL(url)
      } catch (err) {
        console.error('[ArtifactsSidePanel] Download failed:', err)
      }
    }
  }, [spark.download_url, spark.title])

  const codeLanguage = codeLanguageMap[spark.framework] || 'text'

  return (
    <div className="flex flex-col h-full">
      {/* Header — single row: back, title, version, toggle, actions */}
      <div className="flex items-center gap-2 px-2 py-2 border-b border-border/40 shrink-0">
        <Button variant="ghost" size="icon" className="h-7 w-7 shrink-0" onClick={onBack}>
          <ArrowLeft className="h-4 w-4" />
        </Button>
        <div className="flex items-center gap-1.5 min-w-0 flex-1">
          <span className="text-sm font-medium truncate">{spark.title}</span>
          {versions.length > 1 && (
            <div className="flex items-center gap-0.5 shrink-0">
              <button onClick={handlePreviousVersion} disabled={!hasPreviousVersion} className="p-0.5 hover:bg-muted rounded disabled:opacity-30">
                <ChevronLeft className="h-3 w-3" />
              </button>
              <span className="text-[10px] text-muted-foreground tabular-nums">v{spark.version}</span>
              <button onClick={handleNextVersion} disabled={!hasNextVersion} className="p-0.5 hover:bg-muted rounded disabled:opacity-30">
                <ChevronRight className="h-3 w-3" />
              </button>
            </div>
          )}
        </div>
        <TooltipProvider delayDuration={200}>
          <div className="flex items-center bg-muted/50 rounded-md p-0.5 shrink-0">
            <Tooltip>
              <TooltipTrigger asChild>
                <button
                  onClick={() => setActiveTab('preview')}
                  className={cn(
                    "p-1.5 rounded transition-colors",
                    activeTab === 'preview' ? "bg-background shadow-sm text-foreground" : "text-muted-foreground hover:text-foreground"
                  )}
                >
                  <Eye className="h-3.5 w-3.5" />
                </button>
              </TooltipTrigger>
              <TooltipContent side="bottom"><p>Preview</p></TooltipContent>
            </Tooltip>
            <Tooltip>
              <TooltipTrigger asChild>
                <button
                  onClick={() => setActiveTab('code')}
                  className={cn(
                    "p-1.5 rounded transition-colors",
                    activeTab === 'code' ? "bg-background shadow-sm text-foreground" : "text-muted-foreground hover:text-foreground"
                  )}
                >
                  <Code2 className="h-3.5 w-3.5" />
                </button>
              </TooltipTrigger>
              <TooltipContent side="bottom"><p>Code</p></TooltipContent>
            </Tooltip>
          </div>
        </TooltipProvider>
        {lastError && sendSparkFixRequest && sparksEnabled && (
          <Button variant="default" size="sm" className="h-7 px-2 text-[11px]" onClick={handleAskAIToFix} disabled={isFixing}>
            <Zap className="h-3 w-3 mr-1" />
            Fix
          </Button>
        )}
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="icon" className="h-7 w-7 shrink-0">
              <MoreHorizontal className="h-4 w-4" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem onClick={handleRefresh}>
              <RefreshCw className="h-4 w-4 mr-2" />
              Refresh
            </DropdownMenuItem>
            <DropdownMenuItem onClick={handleCopy}>
              <Copy className="h-4 w-4 mr-2" />
              Copy code
            </DropdownMenuItem>
            {spark.download_url && (
              <DropdownMenuItem onClick={handleDownload}>
                <Download className="h-4 w-4 mr-2" />
                Download
              </DropdownMenuItem>
            )}
            <IgniteMenuItems ignite={ignite} />
          </DropdownMenuContent>
        </DropdownMenu>
        <IgniteDialogs ignite={ignite} />
      </div>

      {/* Content — takes all remaining space */}
      {activeTab === 'preview' ? (
        <div className="flex-1 min-h-0 overflow-hidden">
          {isFixing ? (
            <div className="h-full flex flex-col items-center justify-center bg-muted/30">
              <RefreshCw className="h-8 w-8 animate-spin text-primary mb-3" />
              <p className="text-sm font-medium">Asking AI to fix...</p>
            </div>
          ) : (
            <SparkRenderer
              key={renderKey}
              code={spark.code}
              assets={spark.assets}
              framework={spark.framework}
              title={spark.title}
              downloadUrl={spark.download_url}
              hideHeader
              className="h-full w-full"
              onError={handleSparkError}
            />
          )}
        </div>
      ) : (
        <div className="flex-1 min-h-0 flex flex-col overflow-hidden">
          <div className="flex items-center justify-between px-4 py-2.5 bg-[#0d1117] shrink-0">
            <span className="text-xs font-mono text-slate-400 truncate">
              {spark.title.toLowerCase().replace(/\s+/g, '-')}.{codeLanguage}
            </span>
            <button
              className="flex items-center gap-1.5 text-xs text-slate-400 hover:text-slate-200 rounded px-2 py-1 hover:bg-slate-700/50"
              onClick={handleCopy}
            >
              {copied ? <Check className="h-3.5 w-3.5 text-brand-400" /> : <Copy className="h-3.5 w-3.5" />}
              <span>{copied ? 'Copied' : 'Copy'}</span>
            </button>
          </div>
          <div className="flex-1 overflow-auto bg-[#0d1117]">
            <style>{`.spark-code-content * { background-color: transparent !important; border: none !important; }`}</style>
            <div className="px-4 pb-4 spark-code-content">
              <SyntaxHighlighter
                language={codeLanguage}
                style={codeTheme.style}
                showLineNumbers={false}
                wrapLongLines={false}
                customStyle={{ margin: 0, padding: 0, background: 'transparent', fontSize: '0.875rem', lineHeight: '1.7' }}
              >
                {spark.code.trim()}
              </SyntaxHighlighter>
            </div>
          </div>
        </div>
      )}

    </div>
  )
}

// ============================================================================
// Image Components
// ============================================================================

function ImageCard({ asset, isSelected, onClick }: { asset: Asset; isSelected: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className={cn(
        'w-full text-left rounded-xl border transition-all group overflow-hidden',
        'hover:bg-accent/30 hover:border-brand-500/50',
        isSelected ? 'bg-brand-500/15 border-brand-500/50' : 'bg-card/50 border-border/40'
      )}
    >
      <div className="aspect-video relative bg-black/20">
        <AssetImage assetId={asset.id} alt={asset.generation_prompt || 'Generated image'} className="w-full h-full object-cover" />
      </div>
      <div className="p-3">
        <div className="text-xs text-muted-foreground line-clamp-2">{asset.generation_prompt || 'Generated image'}</div>
        <div className="flex items-center gap-2 mt-1.5">
          <span className="text-[10px] uppercase tracking-wider font-medium px-1.5 py-0.5 rounded bg-brand-500/10 text-brand-500">
            {asset.width}×{asset.height}
          </span>
        </div>
      </div>
    </button>
  )
}

// ============================================================================
// Video Components
// ============================================================================

function VideoCard({ asset, isSelected, onClick }: { asset: Asset; isSelected: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className={cn(
        'w-full text-left rounded-xl border transition-all group overflow-hidden',
        'hover:bg-accent/30 hover:border-purple-500/50',
        isSelected ? 'bg-purple-500/15 border-purple-500/50' : 'bg-card/50 border-border/40'
      )}
    >
      <div className="aspect-video relative bg-black/20">
        <VideoThumbnail assetId={asset.id} className="w-full h-full" alt={asset.generation_prompt || 'Video'} />
        <div className="absolute inset-0 flex items-center justify-center bg-black/20">
          <Play className="w-8 h-8 text-white/80" />
        </div>
      </div>
      <div className="p-3">
        <div className="text-xs text-muted-foreground line-clamp-2">{asset.generation_prompt || 'Generated video'}</div>
        <div className="flex items-center gap-2 mt-1.5">
          <span className="text-[10px] uppercase tracking-wider font-medium px-1.5 py-0.5 rounded bg-purple-500/10 text-purple-500">
            {asset.duration_seconds ? `${asset.duration_seconds}s` : 'Video'}
          </span>
        </div>
      </div>
    </button>
  )
}

// ============================================================================
// App Components
// ============================================================================

function AppCard({ app, isRunning, onClick }: { app: AppListItem; isRunning?: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className={cn(
        'w-full text-left p-3 rounded-xl border transition-all group',
        'hover:bg-accent/30 hover:border-border/60',
        'bg-card/50 border-border/40'
      )}
    >
      <div className="flex items-center gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="font-medium text-sm truncate">{app.title}</span>
            {isRunning && (
              <span className="relative flex h-2 w-2 shrink-0">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
                <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500" />
              </span>
            )}
          </div>
          <div className="flex items-center gap-2 mt-1.5">
            <span className="text-[10px] uppercase tracking-wider font-medium px-1.5 py-0.5 rounded bg-orange-500/10 text-orange-500">
              App
            </span>
            {app.version > 1 && (
              <span className="text-xs text-muted-foreground">v{app.version}</span>
            )}
          </div>
        </div>
      </div>
    </button>
  )
}

function InfoRow({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="flex items-center justify-between px-4 py-2.5 text-[13px]">
      <span className="text-muted-foreground/70">{label}</span>
      <span className="text-foreground/90 truncate ml-6 max-w-[220px]">{value}</span>
    </div>
  )
}

function AppPanelDetail({
  app,
  onBack,
}: {
  app: AppListItem
  onBack: () => void
}) {
  const { toast } = useToast()
  const closePanel = useArtifactsPanelStore((s) => s.closePanel)
  const previewState = useAppsStore((s) => s.previewStates[app.id])
  const setPreviewState = useAppsStore((s) => s.setPreviewState)
  const clearPreviewState = useAppsStore((s) => s.clearPreviewState)

  const isRunning = previewState?.running ?? false
  const isLoading = previewState?.loading ?? false

  // On mount, sync preview status with backend — clears stale Zustand state
  useEffect(() => {
    appsAPI.previewStatus(app.id).then((st) => {
      if (st.running) {
        setPreviewState(app.id, { running: true, port: st.port, loading: false })
      } else {
        clearPreviewState(app.id)
      }
    })
  }, [app.id, setPreviewState, clearPreviewState])

  const handleStart = useCallback(async () => {
    setPreviewState(app.id, { loading: true })
    try {
      const result = await appsAPI.startPreview(app.id)
      setPreviewState(app.id, { running: true, port: result.port, loading: false })
      // Dispatch event so PreviewSidePanel opens with the iframe
      window.dispatchEvent(new CustomEvent('preview:started', { detail: result }))
      toast({ title: 'Dev server started' })
      // Close creations panel — preview is shown in the dev server panel
      closePanel()
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
  }, [app.id, setPreviewState, toast, closePanel])

  const formattedDate = new Date(app.created_at).toLocaleDateString('en-US', {
    month: 'long', day: 'numeric', year: 'numeric',
  })

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center gap-2 px-2 py-2 border-b border-border/40 shrink-0">
        <Button variant="ghost" size="icon" className="h-7 w-7 shrink-0" onClick={onBack}>
          <ArrowLeft className="h-4 w-4" />
        </Button>
        <div className="flex items-center gap-1.5 min-w-0 flex-1">
          <Rocket className="h-4 w-4 text-orange-500 shrink-0" />
          <span className="text-sm font-medium truncate">{app.title}</span>
          {app.version > 1 && (
            <span className="text-[10px] text-muted-foreground">v{app.version}</span>
          )}
        </div>
        <Button
          variant="default"
          size="sm"
          className="h-7 px-2.5 text-[11px]"
          onClick={handleStart}
          disabled={isLoading || isRunning}
        >
          {isLoading ? (
            <Loader2 className="h-3 w-3 animate-spin mr-1" />
          ) : isRunning ? (
            <Play className="h-3 w-3 mr-1" />
          ) : (
            <Play className="h-3 w-3 mr-1" />
          )}
          {isRunning ? 'Running' : 'Run'}
        </Button>
      </div>

      {/* Info section — always visible */}
      <ScrollArea className="flex-1">
        <div className="p-4 space-y-4">
          {isRunning && (
            <div className="flex items-center gap-2 text-sm">
              <span className="relative flex h-2 w-2">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
                <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500" />
              </span>
              <span className="text-emerald-500 text-xs">Running — preview open in Dev Server panel</span>
            </div>
          )}
          <div className="rounded-xl bg-muted/20 border border-border/30 divide-y divide-border/20">
            <InfoRow label="Command" value={<code className="text-xs">npm run dev</code>} />
            <InfoRow label="Framework" value={<span className="capitalize">{app.spark_framework}</span>} />
            <InfoRow label="Source Spark" value={app.spark_title} />
            <InfoRow label="Created" value={formattedDate} />
          </div>
        </div>
      </ScrollArea>
    </div>
  )
}

// ============================================================================
// Panel Size Constants
// ============================================================================

const MIN_PANEL_WIDTH = 350
const MAX_PANEL_WIDTH = 1200
const DEFAULT_PANEL_WIDTH = 400

// ============================================================================
// Main Component
// ============================================================================

export function ArtifactsSidePanel({ chatId, conversationId, sparks, chats, className, sendSparkFixRequest, sparksEnabled, isLoading, onIgnite }: ArtifactsSidePanelProps) {
  const {
    isPanelOpen,
    activeSection,
    selectedSparkId,
    selectedAppId,
    setPanelOpen,
    setActiveSection,
    setSelectedSparkId,
    setSelectedAppId,
    setAssetCounts,
    backToList,
    closePanel,
  } = useArtifactsPanelStore()

  const isMobile = useUIStore((state) => state.isMobile)

  // Multi-chat mode
  const isMultiChatMode = chats && chats.length > 1
  const [selectedChatId, setSelectedChatId] = useState<string>(chats?.[0]?.id || chatId)

  useEffect(() => {
    if (chats && chats.length > 0) {
      const validChatIds = chats.map(c => c.id)
      if (!validChatIds.includes(selectedChatId)) {
        setSelectedChatId(chats[0].id)
      }
    }
  }, [chats, selectedChatId])

  const effectiveChatId = isMultiChatMode ? selectedChatId : chatId
  const effectiveSparks = useMemo(() => {
    if (isMultiChatMode && chats) {
      const selectedChat = chats.find(c => c.id === selectedChatId)
      return selectedChat?.sparks || []
    }
    return sparks
  }, [isMultiChatMode, chats, selectedChatId, sparks])

  // Resizable panel state
  const [panelWidth, setPanelWidth] = useState(DEFAULT_PANEL_WIDTH)
  const [isResizing, setIsResizing] = useState(false)
  const resizeRef = useRef<HTMLDivElement>(null)

  // Assets state
  const [images, setImages] = useState<Asset[]>([])
  const [videos, setVideos] = useState<Asset[]>([])
  const [isLoadingAssets, setIsLoadingAssets] = useState(false)

  // Apps state
  const [apps, setApps] = useState<AppListItem[]>([])
  const previewStates = useAppsStore((s) => s.previewStates)

  // Modal state
  const [imageModalOpen, setImageModalOpen] = useState(false)
  const [videoModalOpen, setVideoModalOpen] = useState(false)
  const [currentImageIndex, setCurrentImageIndex] = useState(0)
  const [currentVideoIndex, setCurrentVideoIndex] = useState(0)

  // Loaded spark for version navigation
  const [loadedSpark, setLoadedSpark] = useState<SparkDefinition | null>(null)

  // Mobile fullscreen spark
  const [mobileFullscreenSpark, setMobileFullscreenSpark] = useState<SparkDefinition | null>(null)

  // Fetch assets
  useEffect(() => {
    if (!effectiveChatId || effectiveChatId.includes('temp') || effectiveChatId.length < 36) {
      setImages([]); setVideos([]); setAssetCounts(0, 0)
      return
    }
    setIsLoadingAssets(true)
    assetsAPI.listByChat(effectiveChatId)
      .then((assets) => {
        const imageAssets = assets.filter((a) => (a.asset_type === 'image' || a.asset_type === 'generated') && a.generation_prompt)
        const videoAssets = assets.filter((a) => a.asset_type === 'video' && a.generation_prompt)
        setImages(imageAssets)
        setVideos(videoAssets)
        setAssetCounts(imageAssets.length, videoAssets.length)
      })
      .catch((error) => console.error('Failed to fetch assets:', error))
      .finally(() => setIsLoadingAssets(false))
  }, [effectiveChatId, setAssetCounts])

  // Fetch apps for this chat
  useEffect(() => {
    if (!effectiveChatId || effectiveChatId.includes('temp') || effectiveChatId.length < 36) {
      setApps([])
      return
    }
    appsAPI.list({ chat_id: effectiveChatId })
      .then((res) => setApps(res.results))
      .catch(() => setApps([]))
  }, [effectiveChatId])

  // Cleanup: stop previews on unmount / tab close
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

  // Available sections
  const availableSections = useMemo(() => {
    const sections: { id: ArtifactSection; label: string; count: number; icon: typeof Zap }[] = []
    if (effectiveSparks.length > 0) sections.push({ id: 'sparks', label: 'Sparks', count: effectiveSparks.length, icon: Zap })
    if (images.length > 0) sections.push({ id: 'images', label: 'Images', count: images.length, icon: ImageIcon })
    if (videos.length > 0) sections.push({ id: 'videos', label: 'Videos', count: videos.length, icon: Film })
    if (apps.length > 0) sections.push({ id: 'apps', label: 'Apps', count: apps.length, icon: Rocket })
    return sections
  }, [effectiveSparks.length, images.length, videos.length, apps.length])

  useEffect(() => {
    if (availableSections.length > 0) {
      const currentSectionHasContent = availableSections.some((s) => s.id === activeSection)
      if (!currentSectionHasContent) setActiveSection(availableSections[0].id)
    }
  }, [availableSections, activeSection, setActiveSection])

  // Derive selected spark
  const selectedSpark = useMemo(() => {
    if (loadedSpark && loadedSpark.id === selectedSparkId) return loadedSpark
    return effectiveSparks.find((s) => s.id === selectedSparkId) || null
  }, [effectiveSparks, selectedSparkId, loadedSpark])

  const galleryImages: GalleryAsset[] = useMemo(() => images.map((asset) => ({
    ...asset, chat_id: effectiveChatId, chat_name: null, conversation_id: conversationId || null, generation_model_display_name: null,
  })), [images, effectiveChatId, conversationId])

  const galleryVideos: GalleryAsset[] = useMemo(() => videos.map((asset) => ({
    ...asset, chat_id: effectiveChatId, chat_name: null, conversation_id: conversationId || null, generation_model_display_name: null,
  })), [videos, effectiveChatId, conversationId])

  // Derive selected app
  const selectedApp = useMemo(() => {
    if (!selectedAppId) return null
    return apps.find((a) => a.id === selectedAppId) || null
  }, [apps, selectedAppId])

  const handleImageClick = useCallback((index: number) => { setCurrentImageIndex(index); setImageModalOpen(true) }, [])
  const handleVideoClick = useCallback((index: number) => { setCurrentVideoIndex(index); setVideoModalOpen(true) }, [])

  // Mobile: intercept selectedSparkId → fullscreen overlay
  useEffect(() => {
    if (!isMobile || !selectedSparkId) return
    const spark = effectiveSparks.find((s) => s.id === selectedSparkId) || null
    if (spark) {
      setMobileFullscreenSpark(spark)
      setSelectedSparkId(null)
    }
  }, [isMobile, selectedSparkId, effectiveSparks, setSelectedSparkId])

  // Desktop: click spark → select it (shows inline detail)
  // Mobile: click spark → fullscreen overlay
  const handleSparkClick = useCallback((sparkId: string) => {
    if (isMobile) {
      const spark = effectiveSparks.find((s) => s.id === sparkId) || null
      if (spark) setMobileFullscreenSpark(spark)
      return
    }
    setLoadedSpark(null)
    setSelectedSparkId(sparkId)
  }, [isMobile, effectiveSparks, setSelectedSparkId])

  const handleNavigateToVersion = useCallback(async (sparkId: string) => {
    try {
      const spark = await sparksAPI.get(sparkId)
      if (spark) {
        setLoadedSpark({
          id: spark.id, title: spark.title, framework: spark.framework,
          code: spark.code, version: spark.version, download_url: spark.download_url,
        })
        setSelectedSparkId(sparkId)
      }
    } catch (error) {
      console.error('Failed to load spark version:', error)
    }
  }, [setSelectedSparkId])

  // Resize
  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      if (!isResizing) return
      setPanelWidth(Math.min(MAX_PANEL_WIDTH, Math.max(MIN_PANEL_WIDTH, window.innerWidth - e.clientX)))
    }
    const handleMouseUp = () => { setIsResizing(false); document.body.style.cursor = ''; document.body.style.userSelect = '' }
    if (isResizing) {
      document.body.style.cursor = 'col-resize'
      document.body.style.userSelect = 'none'
      document.addEventListener('mousemove', handleMouseMove)
      document.addEventListener('mouseup', handleMouseUp)
    }
    return () => { document.removeEventListener('mousemove', handleMouseMove); document.removeEventListener('mouseup', handleMouseUp) }
  }, [isResizing])

  const handleResizeStart = useCallback((e: React.MouseEvent) => { e.preventDefault(); setIsResizing(true) }, [])

  const hasSelectedSpark = activeSection === 'sparks' && selectedSpark
  const hasSelectedApp = activeSection === 'apps' && selectedApp
  const hasDetailView = hasSelectedSpark || hasSelectedApp

  // When a spark is open, expand to half the screen; otherwise use user-resized width
  const sparkOpenWidth = typeof window !== 'undefined' ? Math.max(MIN_PANEL_WIDTH, Math.floor(window.innerWidth / 2)) : 700
  const effectiveWidth = hasDetailView ? sparkOpenWidth : panelWidth

  // Render content
  const renderContent = () => {
    if (activeSection === 'sparks') {
      // Detail view — spark fills entire panel
      if (selectedSpark) {
        return (
          <SparkPanelDetail
            spark={selectedSpark}
            onBack={backToList}
            onNavigateToVersion={handleNavigateToVersion}
            sendSparkFixRequest={sendSparkFixRequest}
            sparksEnabled={sparksEnabled}
            onIgnite={onIgnite}
          />
        )
      }
      // List view
      return (
        <ScrollArea className="h-full">
          <div className="p-3 space-y-2">
            {effectiveSparks.length === 0 ? (
              <div className="text-center py-8 text-muted-foreground">
                <FileCode2 className="w-8 h-8 mx-auto mb-2 opacity-30" />
                <p className="text-sm">No creations yet</p>
              </div>
            ) : (
              effectiveSparks.map((spark) => (
                <SparkCard key={spark.id} spark={spark} onClick={() => handleSparkClick(spark.id)} />
              ))
            )}
          </div>
        </ScrollArea>
      )
    }

    if (activeSection === 'images') {
      return (
        <ScrollArea className="h-full">
          <div className="p-3 space-y-2">
            {images.length === 0 ? (
              <div className="text-center py-8 text-muted-foreground">
                <ImageIcon className="w-8 h-8 mx-auto mb-2 opacity-30" />
                <p className="text-sm">No images yet</p>
              </div>
            ) : images.map((image, index) => (
              <ImageCard key={image.id} asset={image} isSelected={false} onClick={() => handleImageClick(index)} />
            ))}
          </div>
        </ScrollArea>
      )
    }

    if (activeSection === 'videos') {
      return (
        <ScrollArea className="h-full">
          <div className="p-3 space-y-2">
            {videos.length === 0 ? (
              <div className="text-center py-8 text-muted-foreground">
                <Film className="w-8 h-8 mx-auto mb-2 opacity-30" />
                <p className="text-sm">No videos yet</p>
              </div>
            ) : videos.map((video, index) => (
              <VideoCard key={video.id} asset={video} isSelected={false} onClick={() => handleVideoClick(index)} />
            ))}
          </div>
        </ScrollArea>
      )
    }

    if (activeSection === 'apps') {
      if (selectedApp) {
        return <AppPanelDetail app={selectedApp} onBack={backToList} />
      }
      return (
        <ScrollArea className="h-full">
          <div className="p-3 space-y-2">
            {apps.length === 0 ? (
              <div className="text-center py-8 text-muted-foreground">
                <Rocket className="w-8 h-8 mx-auto mb-2 opacity-30" />
                <p className="text-sm">No apps yet</p>
              </div>
            ) : apps.map((app) => (
              <AppCard
                key={app.id}
                app={app}
                isRunning={previewStates[app.id]?.running}
                onClick={() => setSelectedAppId(app.id)}
              />
            ))}
          </div>
        </ScrollArea>
      )
    }

    return null
  }

  // Mobile: bottom sheet for list, fullscreen overlay for spark detail
  if (isMobile) {
    return (
      <>
      <Sheet open={isPanelOpen} onOpenChange={setPanelOpen}>
        <SheetContent side="bottom" className="rounded-t-2xl border-t-2 p-0 flex flex-col h-[70vh]">
          <div className="flex justify-center pt-3 pb-2 shrink-0">
            <div className="w-10 h-1 rounded-full bg-muted-foreground/30" />
          </div>

          <SheetHeader className="px-4 pb-3 border-b shrink-0">
            <div className="flex items-center justify-between">
              <SheetTitle>Creations</SheetTitle>
            </div>
          </SheetHeader>

          {isMultiChatMode && chats && (
            <div className="px-4 py-2 border-b">
              <div className="flex gap-1 overflow-x-auto scrollbar-none">
                {chats.map((chat) => {
                  const isSelected = chat.id === selectedChatId
                  const sparkCount = chat.sparks.length
                  return (
                    <button
                      key={chat.id}
                      onClick={() => setSelectedChatId(chat.id)}
                      className={cn(
                        'flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-medium transition-colors flex-shrink-0',
                        isSelected ? 'bg-primary text-primary-foreground' : 'bg-muted/50 text-muted-foreground hover:bg-muted'
                      )}
                    >
                      {chat.model ? (
                        <ModelIcon modelName={chat.model.name} modelId={chat.model.model_id} provider={chat.model.provider}
                          modelIconSlug={chat.model.model_icon_slug} modelIconUrl={chat.model.model_icon_url}
                          providerIconSlug={chat.model.provider_icon_slug} providerIconUrl={chat.model.provider_icon_url}
                          size={14} showTooltip={false} />
                      ) : <div className="w-3.5 h-3.5 rounded-full bg-muted-foreground/30" />}
                      {sparkCount > 0 && <span className="opacity-70">({sparkCount})</span>}
                    </button>
                  )
                })}
              </div>
            </div>
          )}

          {availableSections.length > 1 && (
            <div className="px-4 py-2 border-b">
              <div className="flex gap-1">
                {availableSections.map((section) => (
                  <button
                    key={section.id}
                    onClick={() => setActiveSection(section.id)}
                    className={cn(
                      'flex-1 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors flex items-center justify-center gap-1.5',
                      activeSection === section.id ? 'bg-primary text-primary-foreground' : 'bg-muted/50 text-muted-foreground hover:bg-muted'
                    )}
                  >
                    <section.icon className="w-3.5 h-3.5" />
                    {section.label}
                    <span className="opacity-60">({section.count})</span>
                  </button>
                ))}
              </div>
            </div>
          )}

          <div className="flex-1 overflow-hidden flex flex-col min-h-0">
            {renderContent()}
          </div>
        </SheetContent>
      </Sheet>

      {createPortal(
        <>
          <ImageDetailModal isOpen={imageModalOpen} onClose={() => setImageModalOpen(false)} image={galleryImages[currentImageIndex] || null} images={galleryImages} currentIndex={currentImageIndex} onNavigate={setCurrentImageIndex} />
          <VideoDetailModal isOpen={videoModalOpen} onClose={() => setVideoModalOpen(false)} video={galleryVideos[currentVideoIndex] || null} videos={galleryVideos} currentIndex={currentVideoIndex} onNavigate={setCurrentVideoIndex} />
          <SparkFullscreenOverlay
            spark={mobileFullscreenSpark ? { ...mobileFullscreenSpark, version: mobileFullscreenSpark.version ?? 1 } : null}
            open={!!mobileFullscreenSpark} onClose={() => setMobileFullscreenSpark(null)} onIgnite={onIgnite}
            onFix={sparksEnabled && sendSparkFixRequest ? (id, title, error) => {
              sendSparkFixRequest(`Please fix the "${title}" spark component.`, { spark_id: id, spark_title: title, error })
            } : undefined}
          />
        </>,
        document.body
      )}
    </>
    )
  }

  // Desktop: side panel
  return (
    <div
      className={cn('h-full flex flex-col relative overflow-hidden', 'transition-[width] duration-300 ease-in-out', className)}
      style={{ width: isPanelOpen ? effectiveWidth : 0 }}
    >
      <div
        className={cn('h-full border-l border-border/40 bg-card flex flex-col relative', 'transition-transform duration-300 ease-in-out', isPanelOpen ? 'translate-x-0' : 'translate-x-full')}
        style={{ width: effectiveWidth }}
      >
      {/* Resize handle */}
      <div ref={resizeRef} onMouseDown={handleResizeStart}
        className={cn('absolute left-0 top-0 bottom-0 w-1 cursor-col-resize z-10', 'hover:bg-primary/20 transition-colors group flex items-center justify-center', isResizing && 'bg-primary/30')}
      >
        <div className={cn('absolute left-0 w-4 h-12 flex items-center justify-center', 'opacity-0 group-hover:opacity-100 transition-opacity', isResizing && 'opacity-100')}>
          <GripVertical className="w-3 h-3 text-muted-foreground" />
        </div>
      </div>

      {/* Header — only show when NOT viewing a detail (detail has its own header) */}
      {!hasDetailView && (
        <>
          <div className="flex items-center justify-between p-3 border-b border-border/40">
            <span className="font-medium text-sm">Creations</span>
            <Button variant="ghost" size="icon" className="h-7 w-7" onClick={closePanel}>
              <X className="h-4 w-4" />
            </Button>
          </div>

          {isMultiChatMode && chats && (
            <div className="px-3 py-2 border-b border-border/40">
              <div className="flex gap-1 overflow-x-auto scrollbar-none">
                {chats.map((chat) => {
                  const isSelected = chat.id === selectedChatId
                  const sparkCount = chat.sparks.length
                  return (
                    <TooltipProvider key={chat.id}>
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <button onClick={() => setSelectedChatId(chat.id)}
                            className={cn('flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-medium transition-colors flex-shrink-0',
                              isSelected ? 'bg-primary text-primary-foreground' : 'bg-muted/50 text-muted-foreground hover:bg-muted'
                            )}
                          >
                            {chat.model ? (
                              <ModelIcon modelName={chat.model.name} modelId={chat.model.model_id} provider={chat.model.provider}
                                modelIconSlug={chat.model.model_icon_slug} modelIconUrl={chat.model.model_icon_url}
                                providerIconSlug={chat.model.provider_icon_slug} providerIconUrl={chat.model.provider_icon_url}
                                size={14} showTooltip={false} />
                            ) : <div className="w-3.5 h-3.5 rounded-full bg-muted-foreground/30" />}
                            {sparkCount > 0 && <span className="opacity-70">({sparkCount})</span>}
                          </button>
                        </TooltipTrigger>
                        <TooltipContent>
                          {chat.model ? removeProviderPrefix(chat.model.name, chat.model.provider) : 'No model'}
                          {sparkCount > 0 && ` • ${sparkCount} spark${sparkCount !== 1 ? 's' : ''}`}
                        </TooltipContent>
                      </Tooltip>
                    </TooltipProvider>
                  )
                })}
              </div>
            </div>
          )}

          {availableSections.length > 1 && (
            <div className="px-3 py-2 border-b border-border/40">
              <div className="flex gap-1">
                {availableSections.map((section) => (
                  <button key={section.id} onClick={() => setActiveSection(section.id)}
                    className={cn('flex-1 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors flex items-center justify-center gap-1.5',
                      activeSection === section.id ? 'bg-primary text-primary-foreground' : 'bg-muted/50 text-muted-foreground hover:bg-muted'
                    )}
                  >
                    <section.icon className="w-3.5 h-3.5" />
                    {section.label}
                    <span className="opacity-60">({section.count})</span>
                  </button>
                ))}
              </div>
            </div>
          )}
        </>
      )}

      {/* Content */}
      <div className="flex-1 overflow-hidden">
        {renderContent()}
      </div>
      </div>

      {createPortal(
        <>
          <ImageDetailModal isOpen={imageModalOpen} onClose={() => setImageModalOpen(false)} image={galleryImages[currentImageIndex] || null} images={galleryImages} currentIndex={currentImageIndex} onNavigate={setCurrentImageIndex} />
          <VideoDetailModal isOpen={videoModalOpen} onClose={() => setVideoModalOpen(false)} video={galleryVideos[currentVideoIndex] || null} videos={galleryVideos} currentIndex={currentVideoIndex} onNavigate={setCurrentVideoIndex} />
        </>,
        document.body
      )}
    </div>
  )
}

export default ArtifactsSidePanel
