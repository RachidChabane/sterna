/**
 * SparkDisplay Component
 *
 * Displays Spark (interactive component) within chat messages.
 * Desktop: Uses ProcessSection for collapsible inline expansion
 * Mobile: Clicking on a spark opens fullscreen dialog directly
 *
 * Auto-Fix Feature:
 * When a Spark fails to render, the component can automatically request
 * the LLM to fix the code. This happens up to 3 times before showing
 * a manual fix button.
 */

import { useState, useCallback, useEffect } from 'react'
import { Zap, Code2, Copy, Check, Maximize2, RefreshCw, ChevronRight, Loader2, Wrench, MoreHorizontal, Download } from 'lucide-react'
import { cn } from '@/lib/utils'
import { TypeBadge } from '@/lib/type-badges'
import { ProcessSection } from './ProcessSection'
import { SparkRenderer, type SparkAsset } from './SparkRenderer'
import { SparkFullscreenOverlay } from './SparkFullscreenDialog'
import { Button } from '@/components/ui/button'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useToast } from '@/hooks/use-toast'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { useUIStore } from '@/store/uiStore'
import { useSparkAutoFixContext } from './SparkAutoFixContext'
import { useIgniteDeploy, IgniteMenuItems, IgniteDialogs } from '@/components/sparks/IgniteButton'

interface SparkData {
  id: string
  title: string
  framework: 'react' | 'html' | 'svg' | 'markdown' | 'mermaid' | 'pdf' | 'docx' | 'ics' | 'csv'
  code: string
  version: number
  assets?: SparkAsset[]
  dependencies?: string[]
  download_url?: string | null
  is_ignited?: boolean
}

interface SparkDisplayProps {
  sparks: SparkData[]
  className?: string
  onIgnite?: (sparkId: string, sparkTitle: string) => void
}


/**
 * Single Spark item display with preview and code view (Desktop only)
 * Now includes auto-fix functionality for render errors
 */
function SparkItem({ spark, onIgnite }: { spark: SparkData; onIgnite?: (sparkId: string, sparkTitle: string) => void }) {
  const [activeTab, setActiveTab] = useState<'preview' | 'code'>('preview')
  const [copied, setCopied] = useState(false)
  const [fullscreenOpen, setFullscreenOpen] = useState(false)
  const [renderKey, setRenderKey] = useState(0)
  const [lastError, setLastError] = useState<string | null>(null)
  const { toast } = useToast()
  const ignite = useIgniteDeploy({
    sparkId: spark.id,
    sparkTitle: spark.title,
    framework: spark.framework,
    isIgnited: spark.is_ignited,
    onIgnite,
  })

  // Get auto-fix context (may be null if not provided)
  const autoFix = useSparkAutoFixContext()

  // Check auto-fix state for this spark
  const isFixing = autoFix?.isFixing(spark.id) ?? false
  const attempts = autoFix?.getAttempts(spark.id) ?? 0
  const shouldAutoFix = autoFix?.shouldAutoFix(spark.id) ?? false
  const maxAttemptsReached = attempts >= 3

  const handleCopy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(spark.code)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
      toast({
        title: 'Copied',
        description: 'Code copied to clipboard',
      })
    } catch (error) {
      toast({
        title: 'Failed to copy',
        description: 'Could not copy code to clipboard',
        variant: 'destructive',
      })
    }
  }, [spark.code, toast])

  const handleRefresh = useCallback(() => {
    setRenderKey(k => k + 1)
    setLastError(null)
    // Clear error tracking on manual refresh
    autoFix?.clearError(spark.id)
  }, [autoFix, spark.id])

  // Only enable auto-fix for iframe-renderable types (react/html/svg)
  const isIframeType = spark.framework === 'react' || spark.framework === 'html' || spark.framework === 'svg'

  // Handle render errors
  const handleError = useCallback(
    (error: string) => {
      setLastError(error)

      // Register error with auto-fix system (only for iframe types)
      if (isIframeType && autoFix?.isAutoFixEnabled) {
        autoFix.registerError(spark.id, spark.code, error)
      }
    },
    [autoFix, spark.id, spark.code, isIframeType]
  )

  // Handle successful render
  const handleLoad = useCallback(() => {
    setLastError(null)
    // Clear error tracking on successful render
    autoFix?.clearError(spark.id)
  }, [autoFix, spark.id])

  // Trigger auto-fix when conditions are met (only for iframe types)
  useEffect(() => {
    if (isIframeType && lastError && shouldAutoFix && autoFix && !isFixing) {
      // Small delay to ensure the UI has updated
      const timer = setTimeout(() => {
        autoFix.requestFix(spark.id, spark.title, spark.code, lastError)
      }, 500)
      return () => clearTimeout(timer)
    }
  }, [isIframeType, lastError, shouldAutoFix, autoFix, isFixing, spark.id, spark.title, spark.code])

  // Manual fix request (after max attempts)
  const handleManualFix = useCallback(() => {
    if (autoFix && lastError) {
      // Reset attempts and try again
      autoFix.clearError(spark.id)
      autoFix.registerError(spark.id, spark.code, lastError)
      autoFix.requestFix(spark.id, spark.title, spark.code, lastError)
    }
  }, [autoFix, spark.id, spark.title, spark.code, lastError])

  return (
    <div className="space-y-2">
      {/* Header with title and actions */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Zap className="w-4 h-4 text-amber-500" />
          <span className="text-sm font-medium">{spark.title}</span>
          {spark.version > 1 && (
            <span className="text-xs px-1.5 py-0.5 rounded bg-muted text-muted-foreground">
              v{spark.version}
            </span>
          )}
          {/* Auto-fix status indicator */}
          {isFixing && (
            <span className="flex items-center gap-1 text-xs px-1.5 py-0.5 rounded bg-blue-500/10 text-blue-500 border border-blue-500/20">
              <Loader2 className="w-3 h-3 animate-spin" />
              Fixing...
            </span>
          )}
          {maxAttemptsReached && lastError && !isFixing && (
            <span className="text-xs px-1.5 py-0.5 rounded bg-destructive/10 text-destructive border border-destructive/20">
              Fix failed
            </span>
          )}
        </div>
        <div className="flex items-center gap-1">
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7"
            onClick={() => setFullscreenOpen(true)}
            title="Fullscreen"
          >
            <Maximize2 className="h-3.5 w-3.5" />
          </Button>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="icon" className="h-7 w-7">
                <MoreHorizontal className="h-3.5 w-3.5" />
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
              <IgniteMenuItems ignite={ignite} />
            </DropdownMenuContent>
          </DropdownMenu>
          <IgniteDialogs ignite={ignite} />
        </div>
      </div>

      {/* Tabs for Preview/Code */}
      <Tabs value={activeTab} onValueChange={(v) => setActiveTab(v as 'preview' | 'code')}>
        <TabsList className="h-8 p-0.5 bg-muted/50">
          <TabsTrigger value="preview" className="h-7 text-xs px-3 data-[state=active]:bg-background">
            Preview
          </TabsTrigger>
          <TabsTrigger value="code" className="h-7 text-xs px-3 data-[state=active]:bg-background">
            <Code2 className="w-3 h-3 mr-1" />
            Code
          </TabsTrigger>
        </TabsList>

        <TabsContent value="preview" className="mt-2">
          {/* Show fixing overlay when auto-fix is in progress */}
          {isFixing ? (
            <div className="min-h-[200px] rounded-lg border border-border/40 bg-muted/20 flex flex-col items-center justify-center gap-3">
              <Loader2 className="w-6 h-6 animate-spin text-blue-500" />
              <div className="text-center">
                <p className="text-sm font-medium text-foreground/90">Fixing Spark...</p>
                <p className="text-xs text-muted-foreground mt-1">
                  Attempt {attempts} of 3
                </p>
              </div>
            </div>
          ) : (
            <div className="relative">
              <SparkRenderer
                key={renderKey}
                code={spark.code}
                assets={spark.assets}
                framework={spark.framework}
                title={spark.title}
                downloadUrl={spark.download_url}
                className="min-h-[200px]"
                onError={handleError}
                onLoad={handleLoad}
              />
              {/* Manual fix button overlay when max attempts reached */}
              {maxAttemptsReached && lastError && (
                <div className="absolute inset-0 flex flex-col items-center justify-center bg-background/80 backdrop-blur-sm z-10 rounded-lg">
                  <div className="text-center p-4">
                    <p className="text-sm text-destructive font-medium mb-2">
                      Auto-fix failed after 3 attempts
                    </p>
                    <p className="text-xs text-muted-foreground mb-4 max-w-xs">
                      {lastError}
                    </p>
                    <div className="flex gap-2 justify-center">
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={handleRefresh}
                        className="text-xs"
                      >
                        <RefreshCw className="h-3 w-3 mr-1.5" />
                        Retry
                      </Button>
                      {autoFix && (
                        <Button
                          variant="default"
                          size="sm"
                          onClick={handleManualFix}
                          className="text-xs"
                        >
                          <Wrench className="h-3 w-3 mr-1.5" />
                          Ask AI to Fix
                        </Button>
                      )}
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}
        </TabsContent>

        <TabsContent value="code" className="mt-2">
          <div className="relative">
            <Button
              variant="ghost"
              size="sm"
              className="absolute top-2 right-2 h-7 px-2 text-xs gap-1.5 z-10"
              onClick={handleCopy}
            >
              {copied ? (
                <>
                  <Check className="h-3 w-3" />
                  Copied
                </>
              ) : (
                <>
                  <Copy className="h-3 w-3" />
                  Copy
                </>
              )}
            </Button>
            <pre className="p-4 rounded-lg bg-muted/50 border border-border/40 overflow-x-auto text-xs max-h-[400px] overflow-y-auto">
              <code className="text-foreground/90">{spark.code}</code>
            </pre>
          </div>
        </TabsContent>
      </Tabs>

      {/* Fullscreen Dialog - uses shared component */}
      <SparkFullscreenOverlay
        spark={spark}
        open={fullscreenOpen}
        onClose={() => setFullscreenOpen(false)}
      />
    </div>
  )
}

/**
 * Mobile spark trigger - opens fullscreen dialog directly
 */
function MobileSparkTrigger({
  spark,
  onOpen
}: {
  spark: SparkData
  onOpen: () => void
}) {
  return (
    <button
      className="w-full flex items-center gap-2 px-2.5 py-2 transition-colors cursor-pointer rounded-md hover:bg-amber-500/5 border-l-2 border-amber-500/40"
      onClick={onOpen}
    >
      <ChevronRight className="w-3.5 h-3.5 flex-shrink-0 text-muted-foreground group-hover:text-amber-500" />
      <div className="flex-shrink-0 text-amber-500/70">
        <Zap className="w-3.5 h-3.5" />
      </div>
      <span className="text-xs font-medium text-foreground/90 truncate">
        {spark.title}
      </span>
      <TypeBadge type={spark.framework} />
      {spark.version > 1 && (
        <span className="flex-shrink-0 text-xs px-1.5 py-0.5 rounded bg-muted text-muted-foreground">
          v{spark.version}
        </span>
      )}
    </button>
  )
}

/**
 * SparkDisplay - Shows all sparks in a message
 */
export function SparkDisplay({ sparks, className, onIgnite }: SparkDisplayProps) {
  const isMobile = useUIStore((state) => state.isMobile)
  const [selectedSpark, setSelectedSpark] = useState<SparkData | null>(null)

  if (!sparks || sparks.length === 0) return null

  // Mobile: Show triggers that open fullscreen dialog directly
  if (isMobile) {
    return (
      <div className={cn('mt-4 space-y-1', className)}>
        {sparks.map((spark) => (
          <MobileSparkTrigger
            key={spark.id}
            spark={spark}
            onOpen={() => setSelectedSpark(spark)}
          />
        ))}

        {/* Single fullscreen dialog for selected spark */}
        <SparkFullscreenOverlay
          spark={selectedSpark}
          open={selectedSpark !== null}
          onClose={() => setSelectedSpark(null)}
        />
      </div>
    )
  }

  // Desktop: Single spark - render in ProcessSection
  if (sparks.length === 1) {
    return (
      <div className={cn('mt-4', className)}>
        <ProcessSection
          icon={<Zap className="w-3.5 h-3.5" />}
          title={sparks[0].title}
          variant="amber"
          defaultExpanded={true}
        >
          <SparkItem spark={sparks[0]} onIgnite={onIgnite} />
        </ProcessSection>
      </div>
    )
  }

  // Desktop: Multiple sparks - show in expandable section
  return (
    <div className={cn('mt-4', className)}>
      <ProcessSection
        icon={<Zap className="w-3.5 h-3.5" />}
        title="Sparks"
        badge={sparks.length}
        variant="amber"
        defaultExpanded={true}
      >
        <div className="space-y-4">
          {sparks.map((spark) => (
            <div key={spark.id} className="border-b border-border/30 pb-4 last:border-0 last:pb-0">
              <SparkItem spark={spark} onIgnite={onIgnite} />
            </div>
          ))}
        </div>
      </ProcessSection>
    </div>
  )
}

export default SparkDisplay
