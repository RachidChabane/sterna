/**
 * GlobalFeatureToggles Component
 *
 * Global feature toggle buttons for ModelComparisonPage.
 * Displays a single "Features" button with a popover containing
 * feature toggles grouped by subtle visual spacing.
 * Also includes GitHub repo cloning integration.
 */

import { useState } from 'react'
import { Button } from '@/components/ui/button'
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover'
import { Lightbulb, Puzzle, Sparkles, Code2, ImageIcon, Video, Search, Zap, BookOpen } from 'lucide-react'
import { cn } from '@/lib/utils'
import type { MCPServer } from '@/api/mcp'

export interface FeatureState {
  enabled: number
  total: number
  supported: number
}

interface GlobalFeatureTogglesProps {
  // Web Search (Brave Search)
  webSearchState: FeatureState
  onToggleWebSearch: () => void
  hasWebSearchSupport: boolean

  // Reasoning
  reasoningState: FeatureState
  onToggleReasoning: () => void
  hasReasoningSupport: boolean

  // MCP Tools
  mcpToolsState: FeatureState
  onToggleMCPTools: () => void
  hasFunctionSupport: boolean
  activeServers: MCPServer[]

  // File Tools
  fileToolsState: FeatureState
  onToggleFileTools: () => void

  // Image Generation
  imageGenerationState: FeatureState
  onToggleImageGeneration: () => void

  // Video Generation
  videoGenerationState: FeatureState
  onToggleVideoGeneration: () => void

  // Sparks - Interactive React Components
  sparksState: FeatureState
  onToggleSparks: () => void

  // Knowledge Base - RAG with user documents
  knowledgeBaseState: FeatureState
  onToggleKnowledgeBase: () => void
  hasKnowledgeBaseSupport: boolean

  // General
  disabled?: boolean
  onOpenChange?: (open: boolean) => void
}

// Compact toggle item component
interface ToggleItemProps {
  icon: React.ReactNode
  label: string
  description: string
  state: FeatureState
  onToggle: () => void
  disabled?: boolean
  isSupported?: boolean
  activeColor: string
  badge?: React.ReactNode
}

function ToggleItem({
  icon,
  label,
  description,
  state,
  onToggle,
  disabled = false,
  isSupported = true,
  activeColor,
  badge,
}: ToggleItemProps) {
  const { enabled, supported } = state
  const isActive = enabled > 0
  const allEnabled = enabled === supported && supported > 0
  const isDisabled = disabled || !isSupported

  // Generate toggle track color (unified teal)
  const getTrackColor = () => {
    if (!isSupported) return "bg-muted-foreground/10"
    if (!isActive) return "bg-muted-foreground/20"
    return "bg-accent-brand"
  }

  return (
    <div
      className={cn(
        "flex items-center justify-between py-1.5 px-2 rounded-md cursor-pointer transition-colors",
        isDisabled && "opacity-50 cursor-not-allowed",
        !isDisabled && "hover:bg-muted"
      )}
      onClick={isDisabled ? undefined : onToggle}
    >
      <div className="flex items-center gap-2 flex-1 min-w-0">
        <div className={cn(
          "flex-shrink-0",
          isActive ? activeColor : "text-muted-foreground"
        )}>
          {badge ? (
            <div className="relative">
              {icon}
              {badge}
            </div>
          ) : icon}
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1.5">
            <p className="text-sm font-medium truncate">{label}</p>
            {allEnabled && (
              <div className={cn(
                "h-1.5 w-1.5 rounded-full animate-pulse flex-shrink-0",
                getTrackColor()
              )} />
            )}
          </div>
          <p className="text-[11px] text-muted-foreground truncate">{description}</p>
        </div>
      </div>
      <div className={cn(
        "h-5 w-9 rounded-full transition-colors relative flex-shrink-0 ml-2",
        getTrackColor()
      )}>
        <div className={cn(
          "absolute top-0.5 h-4 w-4 rounded-full bg-white transition-transform shadow-sm",
          isActive ? "translate-x-4" : "translate-x-0.5"
        )} />
      </div>
    </div>
  )
}

export function GlobalFeatureToggles({
  webSearchState,
  onToggleWebSearch,
  hasWebSearchSupport,
  reasoningState,
  onToggleReasoning,
  hasReasoningSupport,
  mcpToolsState,
  onToggleMCPTools,
  hasFunctionSupport,
  activeServers,
  fileToolsState,
  onToggleFileTools,
  imageGenerationState,
  onToggleImageGeneration,
  videoGenerationState,
  onToggleVideoGeneration,
  sparksState,
  onToggleSparks,
  knowledgeBaseState,
  onToggleKnowledgeBase,
  hasKnowledgeBaseSupport,
  disabled = false,
  onOpenChange,
}: GlobalFeatureTogglesProps) {
  const [isOpen, setIsOpen] = useState(false)

  const handleOpenChange = (open: boolean) => {
    setIsOpen(open)
    onOpenChange?.(open)
  }

  // Calculate total active features
  const totalActive = [
    webSearchState.enabled > 0,
    reasoningState.enabled > 0,
    mcpToolsState.enabled > 0,
    fileToolsState.enabled > 0,
    imageGenerationState.enabled > 0,
    videoGenerationState.enabled > 0,
    sparksState.enabled > 0,
    knowledgeBaseState.enabled > 0,
  ].filter(Boolean).length

  const hasActiveFeatures = totalActive > 0

  // Helper to generate description text
  const getDescription = (state: FeatureState, defaultText: string, noCompatibleText = 'No compatible models') => {
    const { enabled, total, supported } = state
    if (supported === 0) return noCompatibleText
    return enabled > 0
      ? `${enabled}/${total} chat${total > 1 ? 's' : ''}`
      : defaultText
  }

  return (
    <Popover open={isOpen} onOpenChange={handleOpenChange}>
      <PopoverTrigger asChild>
        <Button
          variant="ghost"
          size="sm"
          disabled={disabled}
          className={cn(
            "group h-7 gap-1 px-2 rounded-md transition-all",
            hasActiveFeatures
              ? "text-accent-brand hover:text-accent-brand/90 hover:bg-accent-brand/10"
              : "text-muted-foreground hover:text-foreground"
          )}
        >
          <Sparkles className="h-3.5 w-3.5" />
          {hasActiveFeatures && (
            <span className="text-[10px] font-medium tabular-nums">{totalActive}</span>
          )}
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-64 p-2" align="end">
        <div>
          {/* Header */}
          <div className="flex items-center justify-between px-2 pb-1.5 mb-1 border-b border-border">
            <h4 className="font-semibold text-sm">Features</h4>
            <span className="text-xs text-muted-foreground">
              {totalActive} active
            </span>
          </div>

          {/* AI + Tools group */}
          <div className="space-y-0.5">
            <ToggleItem
              icon={<Search className="h-4 w-4" />}
              label="Web Search"
              description={getDescription(webSearchState, 'Search web, images, videos')}
              state={webSearchState}
              onToggle={onToggleWebSearch}
              disabled={disabled}
              isSupported={hasWebSearchSupport}
              activeColor="text-emerald-600 dark:text-emerald-400"
            />
            <ToggleItem
              icon={<Lightbulb className="h-4 w-4" />}
              label="Reasoning"
              description={getDescription(reasoningState, `${reasoningState.supported} compatible`)}
              state={reasoningState}
              onToggle={onToggleReasoning}
              disabled={disabled}
              isSupported={hasReasoningSupport}
              activeColor="text-purple-600 dark:text-purple-400"
            />
            <ToggleItem
              icon={<Puzzle className="h-4 w-4" />}
              label="Connectors"
              description={getDescription(
                mcpToolsState,
                activeServers.length > 0 ? `${activeServers.length} available` : 'MCP tools'
              )}
              state={mcpToolsState}
              onToggle={onToggleMCPTools}
              disabled={disabled}
              isSupported={hasFunctionSupport}
              activeColor="text-blue-600 dark:text-blue-400"
              badge={activeServers.length > 0 ? (
                <div className="absolute -top-1 -right-1 h-3 w-3 rounded-full bg-blue-600 dark:bg-blue-500 flex items-center justify-center text-[8px] text-white font-bold">
                  {activeServers.length}
                </div>
              ) : undefined}
            />
            <ToggleItem
              icon={<Code2 className="h-4 w-4" />}
              label="File Tools"
              description={getDescription(fileToolsState, 'Workspace files')}
              state={fileToolsState}
              onToggle={onToggleFileTools}
              disabled={disabled}
              isSupported={hasFunctionSupport}
              activeColor="text-orange-600 dark:text-orange-400"
            />
            <ToggleItem
              icon={<BookOpen className="h-4 w-4" />}
              label="Knowledge Base"
              description={getDescription(knowledgeBaseState, 'Your documents')}
              state={knowledgeBaseState}
              onToggle={onToggleKnowledgeBase}
              disabled={disabled}
              isSupported={hasKnowledgeBaseSupport}
              activeColor="text-cyan-600 dark:text-cyan-400"
            />
          </div>

          {/* Divider */}
          <div className="h-px bg-border/50 my-1.5 mx-2" />

          {/* Generation group */}
          <div className="space-y-0.5">
            <ToggleItem
              icon={<ImageIcon className="h-4 w-4" />}
              label="Image Generation"
              description={getDescription(imageGenerationState, 'Create images')}
              state={imageGenerationState}
              onToggle={onToggleImageGeneration}
              disabled={disabled}
              isSupported={hasFunctionSupport}
              activeColor="text-pink-600 dark:text-pink-400"
            />
            <ToggleItem
              icon={<Video className="h-4 w-4" />}
              label="Video Generation"
              description={getDescription(videoGenerationState, 'Create videos')}
              state={videoGenerationState}
              onToggle={onToggleVideoGeneration}
              disabled={disabled}
              isSupported={hasFunctionSupport}
              activeColor="text-violet-600 dark:text-violet-400"
            />
            <ToggleItem
              icon={<Zap className="h-4 w-4" />}
              label="Sparks"
              description={getDescription(sparksState, 'Interactive components')}
              state={sparksState}
              onToggle={onToggleSparks}
              disabled={disabled}
              isSupported={hasFunctionSupport}
              activeColor="text-amber-600 dark:text-amber-400"
            />
          </div>
        </div>
      </PopoverContent>
    </Popover>
  )
}
