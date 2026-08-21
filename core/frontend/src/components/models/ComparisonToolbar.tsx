/**
 * ComparisonToolbar Component
 *
 * Toolbar for ModelComparisonPage with:
 * - Add/Remove chat buttons
 * - Sync mode toggle
 * - Model filter button
 * - Feature toggles (Web Search, Reasoning, Connectors)
 */

import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Checkbox } from '@/components/ui/checkbox'
import { Label } from '@/components/ui/label'
import {
  Plus,
  Filter,
  X,
  Globe,
  Lightbulb,
  Puzzle,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { FeatureToggleButton } from './FeatureToggleButton'
import { ConnectorsHoverCard } from './ConnectorsHoverCard'
import type { Filters, Chat } from './types'
import type { MCPServer } from '@/api/mcp'

interface ComparisonToolbarProps {
  // Chat management
  chats: Chat[]
  maxChats: number
  onAddChat: () => void
  onRemoveLastChat: () => void

  // Sync mode
  syncMode: boolean
  onToggleSyncMode: (checked: boolean) => void
  canToggleSyncMode: boolean

  // Filters
  showFilters: boolean
  onToggleFilters: () => void
  hasActiveFilters: boolean
  filters: Filters
  onClearFilters: () => void

  // Feature toggles
  webSearchState: { enabled: number; total: number; supported: number }
  onToggleWebSearch: () => void
  reasoningState: { enabled: number; total: number; supported: number }
  onToggleReasoning: () => void
  mcpToolsState: { enabled: number; total: number; supported: number }
  onToggleMCPTools: () => void
  hasReasoningSupport: () => boolean
  hasFunctionSupport: () => boolean

  // MCP Connectors
  activeServers: MCPServer[]
}

export function ComparisonToolbar({
  chats,
  maxChats,
  onAddChat,
  onRemoveLastChat,
  syncMode,
  onToggleSyncMode,
  canToggleSyncMode,
  showFilters,
  onToggleFilters,
  hasActiveFilters,
  filters,
  onClearFilters,
  webSearchState,
  onToggleWebSearch,
  reasoningState,
  onToggleReasoning,
  mcpToolsState,
  onToggleMCPTools,
  hasReasoningSupport,
  hasFunctionSupport,
  activeServers,
}: ComparisonToolbarProps) {
  return (
    <div className="px-4 space-y-3 flex-shrink-0">
      {/* Controls Row */}
      <div className="flex items-center gap-2 flex-wrap">
        {/* Add/Remove Buttons */}
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={onAddChat}
            disabled={chats.length >= maxChats}
          >
            <Plus className="h-4 w-4 mr-1.5" />
            Add ({chats.length}/{maxChats})
          </Button>

          {chats.length > 1 && (
            <Button
              variant="outline"
              size="sm"
              onClick={onRemoveLastChat}
            >
              <X className="h-4 w-4 mr-1.5" />
              Remove
            </Button>
          )}
        </div>

        {/* Sync Mode Toggle */}
        <div className="flex items-center space-x-2 px-3 py-1.5 rounded-md bg-secondary/30">
          <Checkbox
            id="sync-mode"
            checked={syncMode}
            onCheckedChange={onToggleSyncMode}
            disabled={!canToggleSyncMode}
          />
          <Label
            htmlFor="sync-mode"
            className={cn(
              "text-sm cursor-pointer select-none",
              !canToggleSyncMode && "opacity-50 cursor-not-allowed"
            )}
          >
            Sync Mode
          </Label>
        </div>

        {/* Model Filter Button */}
        <Button
          variant={hasActiveFilters ? "secondary" : "outline"}
          size="sm"
          onClick={onToggleFilters}
          className={cn(showFilters && "bg-secondary")}
        >
          <Filter className="h-4 w-4 mr-1.5" />
          Filters
          {hasActiveFilters && (
            <>
              <Badge
                variant="default"
                className="ml-2 px-1.5 min-w-5 h-5 flex items-center justify-center"
              >
                {(filters.provider ? 1 : 0) + (filters.input_modalities?.length || 0)}
              </Badge>
              <Button
                variant="ghost"
                size="sm"
                onClick={(e) => {
                  e.stopPropagation()
                  onClearFilters()
                }}
                className="h-4 w-4 p-0 ml-1.5 hover:bg-transparent"
              >
                <X className="h-3 w-3" />
              </Button>
            </>
          )}
        </Button>

        <div className="h-6 w-px bg-border mx-1" />

        {/* Global Feature Toggles */}
        <div className="flex items-center gap-2">
          {/* Global Web Search Toggle */}
          <FeatureToggleButton
            enabled={webSearchState.enabled}
            total={webSearchState.total}
            supported={webSearchState.supported}
            icon={Globe}
            label="Web"
            colors={{
              active: "bg-green-500/10 border-green-500/50 text-green-700 dark:text-green-400 hover:bg-green-500/20 hover:border-green-500",
              partial: "bg-green-500/5 border-green-500/30 text-green-600 dark:text-green-500 hover:bg-green-500/10",
              inactive: "bg-background border-border text-muted-foreground hover:bg-muted",
              iconActive: "text-green-600 dark:text-green-400",
              iconPartial: "text-green-500",
              iconInactive: "text-muted-foreground",
            }}
            onClick={onToggleWebSearch}
            disabled={chats.length === 0}
            tooltipTitle={(state) => {
              if (state === 'all') return 'Web Search Enabled'
              if (state === 'some') return 'Web Search Partially Enabled'
              return 'Web Search Disabled'
            }}
            tooltipDescription={(state) => {
              if (state === 'all') return `All ${webSearchState.supported} compatible models have web search enabled`
              if (state === 'some') return `${webSearchState.enabled} of ${webSearchState.supported} compatible models have web search enabled`
              if (webSearchState.supported === 0) return 'No compatible models selected'
              return 'Click to enable web search for all compatible models'
            }}
          />

          {/* Global Reasoning Toggle */}
          <FeatureToggleButton
            enabled={reasoningState.enabled}
            total={reasoningState.total}
            supported={reasoningState.supported}
            icon={Lightbulb}
            label="Reasoning"
            colors={{
              active: "bg-purple-500/10 border-purple-500/50 text-purple-700 dark:text-purple-400 hover:bg-purple-500/20 hover:border-purple-500",
              partial: "bg-purple-500/5 border-purple-500/30 text-purple-600 dark:text-purple-500 hover:bg-purple-500/10",
              inactive: "bg-background border-border text-muted-foreground hover:bg-muted",
              iconActive: "text-purple-600 dark:text-purple-400",
              iconPartial: "text-purple-500",
              iconInactive: "text-muted-foreground",
            }}
            onClick={onToggleReasoning}
            disabled={chats.length === 0 || !hasReasoningSupport()}
            tooltipTitle={(state) => {
              if (state === 'all') return 'Reasoning Enabled'
              if (state === 'some') return 'Reasoning Partially Enabled'
              return 'Reasoning Disabled'
            }}
            tooltipDescription={(state) => {
              if (state === 'all') return `All ${reasoningState.supported} compatible models have reasoning enabled`
              if (state === 'some') return `${reasoningState.enabled} of ${reasoningState.supported} compatible models have reasoning enabled`
              if (reasoningState.supported === 0) return 'No reasoning-capable models selected'
              return 'Click to enable reasoning for all compatible models'
            }}
          />

          {/* Global Connectors Toggle */}
          <ConnectorsHoverCard
            activeServers={activeServers}
            enabled={mcpToolsState.enabled}
            total={mcpToolsState.total}
            supported={mcpToolsState.supported}
          >
            <div className="relative inline-flex">
              <FeatureToggleButton
                enabled={mcpToolsState.enabled}
                total={mcpToolsState.total}
                supported={mcpToolsState.supported}
                icon={Puzzle}
                label="Connectors"
                colors={{
                  active: "bg-blue-500/10 border-blue-500/50 text-blue-700 dark:text-blue-400 hover:bg-blue-500/20 hover:border-blue-500",
                  partial: "bg-blue-500/5 border-blue-500/30 text-blue-600 dark:text-blue-500 hover:bg-blue-500/10",
                  inactive: "bg-background border-border text-muted-foreground hover:bg-muted",
                  iconActive: "text-blue-600 dark:text-blue-400",
                  iconPartial: "text-blue-500",
                  iconInactive: "text-muted-foreground",
                }}
                onClick={onToggleMCPTools}
                disabled={chats.length === 0 || !hasFunctionSupport()}
                tooltipTitle={(state) => {
                  if (state === 'all') return 'Connectors Enabled'
                  if (state === 'some') return 'Connectors Partially Enabled'
                  return 'Connectors Disabled'
                }}
                tooltipDescription={(state) => {
                  if (state === 'all') return `All ${mcpToolsState.supported} compatible models have connectors enabled`
                  if (state === 'some') return `${mcpToolsState.enabled} of ${mcpToolsState.supported} compatible models have connectors enabled`
                  if (mcpToolsState.supported === 0) return 'No function-capable models selected'
                  return 'Click to enable connectors for all compatible models'
                }}
              />
              {activeServers.length > 0 && (
                <Badge
                  className="absolute -top-1 -right-1 h-4 min-w-4 px-1 flex items-center justify-center text-[10px] font-semibold bg-blue-600 dark:bg-blue-500 text-white border-0"
                >
                  {activeServers.length}
                </Badge>
              )}
            </div>
          </ConnectorsHoverCard>
        </div>
      </div>
    </div>
  )
}
