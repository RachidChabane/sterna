/**
 * SparkFullscreenDialog Component
 *
 * Shared fullscreen dialog for viewing Sparks.
 * Used in both SparksPage (gallery) and SparkDisplay (chats).
 */

import { useState, useCallback, useEffect } from 'react'
import { useNavigate } from '@tanstack/react-router'
import {
  Code2,
  Copy,
  Check,
  ChevronLeft,
  ChevronRight,
  Download,
  ExternalLink,
  Eye,
  MoreHorizontal,
  RefreshCw,
  Trash2,
  X,
  Zap,
} from 'lucide-react'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { cn } from '@/lib/utils'
import { TypeBadge } from '@/lib/type-badges'
import { useSettingsStore } from '@/store/settingsStore'
import { getCodeTheme } from '@/constants/codeThemes'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
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
import { SparkRenderer, type SparkAsset } from './SparkRenderer'
import { sparksAPI } from '@/api/sparks'
import { useUIStore } from '@/store/uiStore'
import { useToast } from '@/hooks/use-toast'
import { useIgniteDeploy, IgniteMenuItems, IgniteDialogs } from '@/components/sparks/IgniteButton'

interface SparkData {
  id: string
  title: string
  framework: 'react' | 'html' | 'svg' | 'markdown' | 'mermaid' | 'pdf' | 'docx' | 'ics' | 'csv' | string
  code: string
  version: number
  conversation_id?: string | null
  assets?: SparkAsset[]
  dependencies?: string[]
  download_url?: string | null
  is_ignited?: boolean
}

interface SparkVersion {
  id: string
  version: number
}

interface SparkFullscreenDialogProps {
  spark: SparkData | null
  open: boolean
  onOpenChange: (open: boolean) => void
  /** Version history for navigation */
  versions?: SparkVersion[]
  /** Callback when navigating to a different version */
  onNavigateVersion?: (sparkId: string) => void
  /** Show delete button and callback */
  onDelete?: () => void
  /** Show go to source button */
  showSourceLink?: boolean
  /** Spark ignite callback */
  onIgnite?: (sparkId: string, sparkTitle: string) => void
}


// Get language for syntax highlighting
const getCodeLanguage = (framework: string) => {
  switch (framework) {
    case 'react': return 'tsx'
    case 'html': return 'html'
    case 'svg': return 'xml'
    case 'markdown': return 'markdown'
    case 'mermaid': return 'mermaid'
    case 'csv': return 'csv'
    case 'ics': return 'text'
    case 'pdf': return 'python'
    case 'docx': return 'python'
    case 'xlsx': return 'python'
    default: return 'text'
  }
}

export function SparkFullscreenDialog({
  spark,
  open,
  onOpenChange,
  versions = [],
  onNavigateVersion,
  onDelete,
  showSourceLink = false,
  onIgnite,
}: SparkFullscreenDialogProps) {
  const navigate = useNavigate()
  const { toast } = useToast()
  const isMobile = useUIStore((state) => state.isMobile)
  const codeThemeId = useSettingsStore((state) => state.codeTheme)
  const codeTheme = getCodeTheme(codeThemeId)

  const [activeTab, setActiveTab] = useState<'preview' | 'code'>('preview')
  const [copied, setCopied] = useState(false)
  const [renderError, setRenderError] = useState<string | null>(null)

  const ignite = useIgniteDeploy({
    sparkId: spark?.id ?? '',
    sparkTitle: spark?.title,
    framework: spark?.framework,
    conversationId: spark?.conversation_id,
    isIgnited: spark?.is_ignited,
    onIgnite,
  })

  // Clear error when spark changes
  useEffect(() => {
    setRenderError(null)
  }, [spark?.id])

  // Handle render error from SparkRenderer
  const handleRenderError = useCallback((error: string) => {
    setRenderError(error)
  }, [])

  // Handle successful render - clear error
  const handleRenderLoad = useCallback(() => {
    setRenderError(null)
  }, [])

  // Navigate to chat with fix params
  const handleRequestFix = useCallback(() => {
    if (!spark?.conversation_id || !renderError) return
    navigate({
      to: '/chats',
      search: {
        conversation: spark.conversation_id,
        fix_spark: spark.id,
        fix_error: renderError,
      },
    })
    onOpenChange(false)
  }, [spark, renderError, navigate, onOpenChange])

  // Version navigation
  const currentVersionIndex = versions.findIndex((v) => v.id === spark?.id)
  const hasPreviousVersion = currentVersionIndex < versions.length - 1
  const hasNextVersion = currentVersionIndex > 0

  const handlePreviousVersion = useCallback(() => {
    if (hasPreviousVersion && versions.length > 0 && onNavigateVersion) {
      const prevVersion = versions[currentVersionIndex + 1]
      onNavigateVersion(prevVersion.id)
    }
  }, [versions, currentVersionIndex, hasPreviousVersion, onNavigateVersion])

  const handleNextVersion = useCallback(() => {
    if (hasNextVersion && versions.length > 0 && onNavigateVersion) {
      const nextVersion = versions[currentVersionIndex - 1]
      onNavigateVersion(nextVersion.id)
    }
  }, [versions, currentVersionIndex, hasNextVersion, onNavigateVersion])

  // Determine if this type is renderable vs downloadable for tab label
  const isRenderableType = spark ? ['react', 'html', 'svg', 'markdown', 'mermaid'].includes(spark.framework) : true

  // Copy code
  const handleCopy = useCallback(async () => {
    if (!spark) return
    try {
      await navigator.clipboard.writeText(spark.code)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
      toast({
        title: 'Copied',
        description: 'Content copied to clipboard',
      })
    } catch {
      toast({
        title: 'Failed to copy',
        description: 'Could not copy to clipboard',
        variant: 'destructive',
      })
    }
  }, [spark, toast])

  // Go to source conversation
  const handleGoToSource = useCallback(() => {
    if (spark?.conversation_id) {
      navigate({ to: '/chats', search: { conversation: spark.conversation_id } })
      onOpenChange(false)
    }
  }, [spark, navigate, onOpenChange])

  // Download handler - uses download_url if available, otherwise downloads source code
  const handleDownload = useCallback(async () => {
    if (!spark) return
    if (spark.download_url) {
      try {
        const token = localStorage.getItem('access_token')
        const resp = await fetch(spark.download_url, {
          headers: token ? { Authorization: `Bearer ${token}` } : {},
        })
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
        const blob = await resp.blob()
        const extMap: Record<string, string> = { csv: 'csv', ics: 'ics', pdf: 'pdf', docx: 'docx', xlsx: 'xlsx' }
        const ext = extMap[spark.framework] || 'bin'
        const filename = `${spark.title.toLowerCase().replace(/\s+/g, '-')}.${ext}`
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = filename
        a.click()
        URL.revokeObjectURL(url)
      } catch (err) {
        console.error('[SparkFullscreen] Download failed:', err)
      }
      return
    }
    // Download source code as file
    const extMap: Record<string, string> = {
      react: 'tsx', html: 'html', svg: 'svg', markdown: 'md', mermaid: 'mmd',
      csv: 'csv', ics: 'ics', pdf: 'py', docx: 'py', xlsx: 'py',
    }
    const ext = extMap[spark.framework] || 'txt'
    const filename = `${spark.title.toLowerCase().replace(/\s+/g, '-')}.${ext}`
    const blob = new Blob([spark.code], { type: 'text/plain' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    a.click()
    URL.revokeObjectURL(url)
  }, [spark])

  if (!spark) return null

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className={cn(
        "flex flex-col p-0 gap-0 z-[60]",
        isMobile
          ? "w-screen h-screen max-w-none rounded-none border-0"
          : "max-w-4xl w-[90vw] h-[85vh]"
      )}>
        {/* Header */}
        <div className={cn(
          "flex items-center border-b flex-shrink-0",
          isMobile ? "h-12 px-3 gap-2" : "h-14 px-4 gap-3"
        )}>
          {/* Title - left aligned */}
          <DialogHeader className="p-0 space-y-0 flex-1 min-w-0 text-left">
            <DialogTitle className={cn(
              "truncate text-left",
              isMobile ? "text-sm font-medium" : "text-base"
            )}>
              {spark.title}
            </DialogTitle>
          </DialogHeader>

          {/* Framework badge */}
          <TypeBadge type={spark.framework} className="shrink-0" />

          {/* Desktop action buttons */}
          {!isMobile && (
            <div className="flex items-center gap-1 shrink-0">
              {renderError && spark.conversation_id && (
                <Button
                  variant="default"
                  size="sm"
                  className="h-8 px-3"
                  onClick={handleRequestFix}
                >
                  <Zap className="h-3.5 w-3.5 mr-1.5" />
                  Fix
                </Button>
              )}
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button variant="ghost" size="icon" className="h-8 w-8">
                    <MoreHorizontal className="h-4 w-4" />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end">
                  <DropdownMenuItem onClick={handleDownload}>
                    <Download className="h-4 w-4 mr-2" />
                    {spark.download_url ? 'Download file' : 'Download source'}
                  </DropdownMenuItem>
                  {showSourceLink && spark.conversation_id && (
                    <DropdownMenuItem onClick={handleGoToSource}>
                      <ExternalLink className="h-4 w-4 mr-2" />
                      Go to source
                    </DropdownMenuItem>
                  )}
                  <IgniteMenuItems ignite={ignite} />
                  {onDelete && (
                    <>
                      <DropdownMenuSeparator />
                      <DropdownMenuItem onClick={onDelete} className="text-destructive focus:text-destructive">
                        <Trash2 className="h-4 w-4 mr-2" />
                        Delete
                      </DropdownMenuItem>
                    </>
                  )}
                </DropdownMenuContent>
              </DropdownMenu>
              <IgniteDialogs ignite={ignite} />
            </div>
          )}

          {/* Spacer for close button */}
          <div className={isMobile ? "w-6" : "w-8"} />
        </div>

        {/* Tabs bar */}
        <Tabs
          value={activeTab}
          onValueChange={(v) => setActiveTab(v as 'preview' | 'code')}
          className="flex-1 flex flex-col overflow-hidden min-h-0"
        >
          <div className={cn(
            "flex items-center justify-between border-b",
            isMobile ? "px-3 py-1.5" : "px-4 py-2"
          )}>
            <TabsList className={cn(
              "p-0.5 bg-muted/50",
              isMobile ? "h-7" : "h-8"
            )}>
              <TabsTrigger
                value="preview"
                className={cn(
                  "data-[state=active]:bg-background",
                  isMobile ? "h-6 px-3 text-xs" : "h-7 px-4 text-sm"
                )}
              >
                Preview
              </TabsTrigger>
              <TabsTrigger
                value="code"
                className={cn(
                  "gap-1.5 data-[state=active]:bg-background",
                  isMobile ? "h-6 px-3 text-xs" : "h-7 px-4 text-sm"
                )}
              >
                <Code2 className={isMobile ? "h-3 w-3" : "h-3.5 w-3.5"} />
                {isRenderableType ? 'Code' : 'Source'}
              </TabsTrigger>
            </TabsList>

            {/* Version navigation - only if multiple versions */}
            {versions.length > 1 && onNavigateVersion && (
              <div className="flex items-center gap-1">
                <button
                  className="p-1 hover:bg-muted rounded disabled:opacity-30"
                  onClick={handlePreviousVersion}
                  disabled={!hasPreviousVersion}
                >
                  <ChevronLeft className="h-4 w-4" />
                </button>
                <span className={cn(
                  "px-1.5 py-0.5 rounded bg-muted text-muted-foreground tabular-nums",
                  isMobile ? "text-[10px]" : "text-xs"
                )}>
                  v{spark.version}
                </span>
                <button
                  className="p-1 hover:bg-muted rounded disabled:opacity-30"
                  onClick={handleNextVersion}
                  disabled={!hasNextVersion}
                >
                  <ChevronRight className="h-4 w-4" />
                </button>
              </div>
            )}

            {/* Single version badge */}
            {versions.length <= 1 && spark.version > 1 && (
              <span className={cn(
                "px-1.5 py-0.5 rounded bg-muted text-muted-foreground",
                isMobile ? "text-[10px]" : "text-xs"
              )}>
                v{spark.version}
              </span>
            )}
          </div>

          {/* Preview tab */}
          <TabsContent
            value="preview"
            className={cn(
              "flex-1 overflow-hidden mt-0 min-h-0",
              isMobile ? "p-2" : "p-4"
            )}
          >
            <SparkRenderer
              code={spark.code}
              assets={spark.assets}
              framework={spark.framework}
              title={spark.title}
              downloadUrl={spark.download_url}
              hideHeader
              className="h-full w-full"
              onError={handleRenderError}
              onLoad={handleRenderLoad}
            />
          </TabsContent>

          {/* Code tab */}
          <TabsContent
            value="code"
            className={cn(
              "flex-1 overflow-hidden mt-0 min-h-0",
              isMobile ? "p-2" : "p-3"
            )}
          >
            <div className={cn(
              "relative h-full flex flex-col overflow-hidden border border-slate-800",
              isMobile ? "rounded-lg" : "rounded-xl"
            )}>
              {/* Code header */}
              <div className={cn(
                "flex items-center justify-between bg-[#0d1117] shrink-0",
                isMobile ? "px-3 py-2" : "px-4 py-3"
              )}>
                <span className={cn(
                  "font-mono text-slate-400 truncate",
                  isMobile ? "text-[10px]" : "text-xs"
                )}>
                  {spark.title.toLowerCase().replace(/\s+/g, '-')}.{getCodeLanguage(spark.framework)}
                </span>
                <button
                  className={cn(
                    "flex items-center gap-1.5 text-slate-400 hover:text-slate-200 rounded px-2 py-1 hover:bg-slate-700/50",
                    isMobile ? "text-[10px]" : "text-xs"
                  )}
                  onClick={handleCopy}
                >
                  {copied ? (
                    <Check className={cn("text-brand-400", isMobile ? "h-3 w-3" : "h-3.5 w-3.5")} />
                  ) : (
                    <Copy className={isMobile ? "h-3 w-3" : "h-3.5 w-3.5"} />
                  )}
                  <span>{copied ? 'Copied' : 'Copy'}</span>
                </button>
              </div>

              {/* Syntax highlighted code */}
              <div className="flex-1 overflow-auto bg-[#0d1117]">
                <div className={cn(
                  "spark-code-content",
                  isMobile ? "px-3 pb-3" : "px-4 pb-4"
                )}>
                  <SyntaxHighlighter
                    language={getCodeLanguage(spark.framework)}
                    style={codeTheme.style}
                    showLineNumbers={false}
                    wrapLines={false}
                    wrapLongLines={false}
                    customStyle={{
                      margin: 0,
                      padding: 0,
                      background: 'transparent',
                      fontSize: isMobile ? '0.7rem' : '0.875rem',
                      lineHeight: isMobile ? '1.5' : '1.7',
                      border: 'none',
                      color: codeTheme.textColor,
                    }}
                    codeTagProps={{
                      style: {
                        fontFamily: "'SF Mono', ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace",
                        backgroundColor: 'transparent',
                        color: codeTheme.textColor,
                      },
                    }}
                  >
                    {spark.code.trim()}
                  </SyntaxHighlighter>
                </div>
              </div>
            </div>
          </TabsContent>
        </Tabs>

        {/* Mobile bottom action bar */}
        {isMobile && (
          <div className="flex items-center justify-between px-3 py-2 border-t bg-muted/30 shrink-0">
            <div className="flex items-center gap-1">
              {renderError && spark.conversation_id && (
                <Button
                  variant="default"
                  size="sm"
                  className="h-8 px-3 text-xs gap-1.5"
                  onClick={handleRequestFix}
                >
                  <Zap className="h-3.5 w-3.5" />
                  Fix
                </Button>
              )}
            </div>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="ghost" size="icon" className="h-8 w-8">
                  <MoreHorizontal className="h-4 w-4" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem onClick={handleDownload}>
                  <Download className="h-4 w-4 mr-2" />
                  {spark.download_url ? 'Download file' : 'Download source'}
                </DropdownMenuItem>
                {showSourceLink && spark.conversation_id && (
                  <DropdownMenuItem onClick={handleGoToSource}>
                    <ExternalLink className="h-4 w-4 mr-2" />
                    Go to source
                  </DropdownMenuItem>
                )}
                <IgniteMenuItems ignite={ignite} />
                {onDelete && (
                  <>
                    <DropdownMenuSeparator />
                    <DropdownMenuItem onClick={onDelete} className="text-destructive focus:text-destructive">
                      <Trash2 className="h-4 w-4 mr-2" />
                      Delete
                    </DropdownMenuItem>
                  </>
                )}
              </DropdownMenuContent>
            </DropdownMenu>
            <IgniteDialogs ignite={ignite} />
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}

// =============================================================================
// True Fullscreen Overlay (used everywhere instead of the dialog)
// =============================================================================

interface SparkFullscreenOverlayProps {
  spark: SparkData | null
  open: boolean
  onClose: () => void
  onIgnite?: (sparkId: string, sparkTitle: string) => void
  /** Called when user clicks Fix on a render error */
  onFix?: (sparkId: string, sparkTitle: string, error: string) => void
}

export function SparkFullscreenOverlay({
  spark,
  open,
  onClose,
  onIgnite,
  onFix,
}: SparkFullscreenOverlayProps) {
  const { toast } = useToast()
  const isMobile = useUIStore((state) => state.isMobile)
  const codeThemeId = useSettingsStore((state) => state.codeTheme)
  const codeTheme = getCodeTheme(codeThemeId)

  const [copied, setCopied] = useState(false)
  const [activeTab, setActiveTab] = useState<'preview' | 'code'>('preview')
  const [renderKey, setRenderKey] = useState(0)
  const [lastError, setLastError] = useState<string | null>(null)

  // Version navigation (self-contained)
  const [internalSpark, setInternalSpark] = useState<SparkData | null>(null)
  const [versions, setVersions] = useState<{ id: string; version: number }[]>([])
  const activeSpark = internalSpark || spark

  const ignite = useIgniteDeploy({
    sparkId: activeSpark?.id ?? '',
    sparkTitle: activeSpark?.title,
    framework: activeSpark?.framework,
    conversationId: activeSpark?.conversation_id,
    isIgnited: activeSpark?.is_ignited,
    onIgnite,
  })

  // Reset when external spark changes
  useEffect(() => {
    setInternalSpark(null)
    setActiveTab('preview')
    setRenderKey(0)
    setLastError(null)
    setCopied(false)
  }, [spark?.id])

  // Fetch versions when open
  useEffect(() => {
    if (!open || !spark?.id) { setVersions([]); return }
    sparksAPI.getVersions(spark.id)
      .then(setVersions)
      .catch(() => setVersions([]))
  }, [open, spark?.id])

  const currentVersionIndex = versions.findIndex((v) => v.id === activeSpark?.id)
  const hasPreviousVersion = currentVersionIndex >= 0 && currentVersionIndex < versions.length - 1
  const hasNextVersion = currentVersionIndex > 0

  const handlePreviousVersion = useCallback(async () => {
    if (!hasPreviousVersion || !versions.length) return
    try {
      const loaded = await sparksAPI.get(versions[currentVersionIndex + 1].id)
      setInternalSpark(loaded)
    } catch (e) {
      console.error('Failed to load version:', e)
    }
  }, [versions, currentVersionIndex, hasPreviousVersion])

  const handleNextVersion = useCallback(async () => {
    if (!hasNextVersion || !versions.length) return
    try {
      const loaded = await sparksAPI.get(versions[currentVersionIndex - 1].id)
      setInternalSpark(loaded)
    } catch (e) {
      console.error('Failed to load version:', e)
    }
  }, [versions, currentVersionIndex, hasNextVersion])

  // Close on Escape
  useEffect(() => {
    if (!open) return
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [open, onClose])

  const handleCopy = useCallback(async () => {
    if (!activeSpark) return
    try {
      await navigator.clipboard.writeText(activeSpark.code)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
      toast({ title: 'Copied to clipboard' })
    } catch {
      toast({ title: 'Failed to copy', variant: 'destructive' })
    }
  }, [activeSpark, toast])

  const handleDownload = useCallback(() => {
    if (!activeSpark) return
    if (activeSpark.download_url) {
      const token = localStorage.getItem('access_token')
      fetch(activeSpark.download_url, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      })
        .then((r) => r.blob())
        .then((blob) => {
          const ext: Record<string, string> = { csv: 'csv', ics: 'ics', pdf: 'pdf', docx: 'docx', xlsx: 'xlsx' }
          const filename = `${activeSpark.title.toLowerCase().replace(/\s+/g, '-')}.${ext[activeSpark.framework] || 'bin'}`
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
    const filename = `${activeSpark.title.toLowerCase().replace(/\s+/g, '-')}.${ext[activeSpark.framework] || 'txt'}`
    const blob = new Blob([activeSpark.code], { type: 'text/plain' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    a.click()
    URL.revokeObjectURL(url)
  }, [activeSpark])

  const handleRefresh = useCallback(() => {
    setRenderKey((k) => k + 1)
    setLastError(null)
  }, [])

  const handleRenderError = useCallback((error: string) => {
    setLastError(error)
  }, [])

  const handleRenderLoad = useCallback(() => {
    setLastError(null)
  }, [])

  const handleFix = useCallback(() => {
    if (activeSpark && lastError && onFix) {
      onFix(activeSpark.id, activeSpark.title, lastError)
    }
  }, [activeSpark, lastError, onFix])

  if (!open || !activeSpark) return null

  return (
    <div className="fixed inset-0 z-[100] bg-background flex flex-col">
      {/* Toolbar */}
      <div className="shrink-0 border-b border-border/30">
        {/* Toolbar: title + version + toggle (desktop inline / mobile row 2) + actions */}
        <div className="flex items-center justify-between px-4 py-2.5 gap-3">
          <div className="flex items-center gap-2.5 min-w-0 flex-1">
            <TypeBadge type={activeSpark.framework} className="shrink-0" />
            <span className={cn(
              "text-foreground font-medium truncate",
              isMobile ? "text-xs" : "text-sm"
            )}>
              {activeSpark.title}
            </span>
            {versions.length > 1 && (
              <div className="flex items-center gap-0.5 shrink-0">
                <button
                  onClick={handlePreviousVersion}
                  disabled={!hasPreviousVersion}
                  className="p-0.5 hover:bg-muted rounded disabled:opacity-30 transition-colors"
                >
                  <ChevronLeft className="h-3.5 w-3.5" />
                </button>
                <span className="text-xs text-muted-foreground px-1 tabular-nums">
                  v{activeSpark.version}
                </span>
                <button
                  onClick={handleNextVersion}
                  disabled={!hasNextVersion}
                  className="p-0.5 hover:bg-muted rounded disabled:opacity-30 transition-colors"
                >
                  <ChevronRight className="h-3.5 w-3.5" />
                </button>
              </div>
            )}
          </div>
          {/* Desktop: toggle inline */}
          {!isMobile && (
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
                  <TooltipContent side="bottom" className="z-[200]"><p>Preview</p></TooltipContent>
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
                  <TooltipContent side="bottom" className="z-[200]"><p>Code</p></TooltipContent>
                </Tooltip>
              </div>
            </TooltipProvider>
          )}
          <div className="flex items-center gap-0.5 shrink-0">
            {lastError && onFix && (
              <Button variant="default" size="sm" className="h-7 px-3" onClick={handleFix}>
                <Zap className="h-3.5 w-3.5 mr-1.5" />
                Fix
              </Button>
            )}
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <button className="inline-flex items-center justify-center h-8 w-8 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted/50 transition-all">
                  <MoreHorizontal className="h-4 w-4" />
                </button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="z-[200]">
                <DropdownMenuItem onClick={handleCopy}>
                  {copied ? <Check className="h-4 w-4 mr-2 text-emerald-400" /> : <Copy className="h-4 w-4 mr-2" />}
                  {copied ? 'Copied' : 'Copy code'}
                </DropdownMenuItem>
                <DropdownMenuItem onClick={handleDownload}>
                  <Download className="h-4 w-4 mr-2" />
                  Download
                </DropdownMenuItem>
                <DropdownMenuItem onClick={handleRefresh}>
                  <RefreshCw className="h-4 w-4 mr-2" />
                  Refresh preview
                </DropdownMenuItem>
                <IgniteMenuItems ignite={ignite} />
              </DropdownMenuContent>
            </DropdownMenu>
            <TooltipProvider delayDuration={200}>
              <Tooltip>
                <TooltipTrigger asChild>
                  <button
                    onClick={onClose}
                    className="inline-flex items-center justify-center h-8 w-8 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted/50 transition-all ml-1"
                  >
                    <X className="h-4 w-4" />
                  </button>
                </TooltipTrigger>
                <TooltipContent side="bottom" className="z-[200]">
                  Close <span className="text-muted-foreground ml-1">Esc</span>
                </TooltipContent>
              </Tooltip>
            </TooltipProvider>
            <IgniteDialogs ignite={ignite} />
          </div>
        </div>
        {/* Mobile: toggle on separate row */}
        {isMobile && (
          <div className="flex items-center gap-1 px-4 pb-2">
            <div className="flex items-center bg-muted/50 rounded-md p-0.5">
              <button
                onClick={() => setActiveTab('preview')}
                className={cn(
                  "px-2.5 py-1 rounded text-xs font-medium transition-colors",
                  activeTab === 'preview' ? "bg-background shadow-sm text-foreground" : "text-muted-foreground hover:text-foreground"
                )}
              >
                Preview
              </button>
              <button
                onClick={() => setActiveTab('code')}
                className={cn(
                  "px-2.5 py-1 rounded text-xs font-medium transition-colors",
                  activeTab === 'code' ? "bg-background shadow-sm text-foreground" : "text-muted-foreground hover:text-foreground"
                )}
              >
                Code
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Content */}
      {activeTab === 'preview' ? (
        <div className="flex-1 min-h-0">
          <SparkRenderer
            key={renderKey}
            code={activeSpark.code}
            assets={activeSpark.assets}
            framework={activeSpark.framework}
            title={activeSpark.title}
            downloadUrl={activeSpark.download_url}
            hideHeader
            className="w-full h-full"
            onError={handleRenderError}
            onLoad={handleRenderLoad}
          />
        </div>
      ) : (
        <div className="flex-1 min-h-0 flex flex-col overflow-hidden">
          <div className={cn(
            "flex items-center justify-between bg-[#0d1117] shrink-0",
            isMobile ? "px-3 py-2" : "px-4 py-3"
          )}>
            <span className={cn(
              "font-mono text-slate-400 truncate",
              isMobile ? "text-[10px]" : "text-xs"
            )}>
              {activeSpark.title.toLowerCase().replace(/\s+/g, '-')}.{getCodeLanguage(activeSpark.framework)}
            </span>
            <button
              className={cn(
                "flex items-center gap-1.5 text-slate-400 hover:text-slate-200 rounded px-2 py-1 hover:bg-slate-700/50",
                isMobile ? "text-[10px]" : "text-xs"
              )}
              onClick={handleCopy}
            >
              {copied ? (
                <Check className={cn("text-brand-400", isMobile ? "h-3 w-3" : "h-3.5 w-3.5")} />
              ) : (
                <Copy className={isMobile ? "h-3 w-3" : "h-3.5 w-3.5"} />
              )}
              <span>{copied ? 'Copied' : 'Copy'}</span>
            </button>
          </div>
          <div className="flex-1 overflow-auto bg-[#0d1117]">
            <style>{`.spark-code-content * { background-color: transparent !important; border: none !important; }`}</style>
            <div className={cn(
              "spark-code-content",
              isMobile ? "px-3 pb-3" : "px-4 pb-4"
            )}>
              <SyntaxHighlighter
                language={getCodeLanguage(activeSpark.framework)}
                style={codeTheme.style}
                showLineNumbers={false}
                wrapLongLines={false}
                customStyle={{
                  margin: 0,
                  padding: 0,
                  background: 'transparent',
                  fontSize: isMobile ? '0.7rem' : '0.875rem',
                  lineHeight: isMobile ? '1.5' : '1.7',
                  border: 'none',
                  color: codeTheme.textColor,
                }}
                codeTagProps={{
                  style: {
                    fontFamily: "'SF Mono', ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace",
                    backgroundColor: 'transparent',
                    color: codeTheme.textColor,
                  },
                }}
              >
                {activeSpark.code.trim()}
              </SyntaxHighlighter>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default SparkFullscreenDialog
