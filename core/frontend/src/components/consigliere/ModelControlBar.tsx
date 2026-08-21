/**
 * Model Control Bar for Consigliere
 *
 * Compact, professional card that displays the current model
 * and provides quick access to model controls (settings, change, browse).
 */

import { useState } from 'react'
import { RefreshCw, Library, ChevronDown, Star, Clock, MoreVertical, X, Trash2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { ModelIcon } from '@/components/models/ModelIcon'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import { Badge } from '@/components/ui/badge'
import { removeProviderPrefix } from '@/lib/model-utils'
import { pricingUtils } from '@/lib/pricing-utils'
import type { ModelCatalogEntry, ModelFavorite, RecentModel } from '@/types/models'
import { cn } from '@/lib/utils'
import { ChatCopyExportItems } from '@/components/models/ChatCopyExportItems'

interface ModelControlBarProps {
  currentModel: ModelCatalogEntry | null
  recentModels?: RecentModel[]
  favorites?: ModelFavorite[]
  onModelChange?: (model: ModelCatalogEntry) => void
  onBrowseClick?: () => void
  // Chat actions matching /chats header menu
  onStop?: () => void
  canStop?: boolean
  onCopyResponses?: () => void
  onCopyMetadata?: () => void
  onExportResponses?: () => void
  onExportMetadata?: () => void
  onClearChat?: () => void
  clearDisabled?: boolean
}

export function ModelControlBar({
  currentModel,
  recentModels = [],
  favorites = [],
  onModelChange,
  onBrowseClick,
  onStop,
  canStop,
  onCopyResponses,
  onCopyMetadata,
  onExportResponses,
  onExportMetadata,
  onClearChat,
  clearDisabled,
}: ModelControlBarProps) {
  const [isDropdownOpen, setIsDropdownOpen] = useState(false)

  // Get actual model objects from recent and favorites
  const recentModelsList = recentModels
    .slice(0, 3) // Show only 3 most recent
    .filter(rm => rm.details) // Only include if we have full details
    .map(rm => rm.details!)

  const favoriteModelsList = favorites
    .filter(f => f.details) // Only include if we have full details
    .map(f => f.details!)

  const handleModelSelect = (model: ModelCatalogEntry) => {
    setIsDropdownOpen(false)
    onModelChange?.(model)
  }

  const isSterna = currentModel?.model_id === 'ornithops/sterna'
  const isFree = !isSterna && currentModel &&
    currentModel.cost_per_1m_prompt === 0 &&
    currentModel.cost_per_1m_completion === 0

  return (
    <div className="bg-card/50 border border-border rounded-lg overflow-hidden hover:bg-card/70 transition-colors">
      <div className="flex items-center justify-between px-4 py-3 gap-4">
        {/* Model Info - Clickable */}
        <DropdownMenu open={isDropdownOpen} onOpenChange={setIsDropdownOpen}>
          <DropdownMenuTrigger asChild>
            <button className="flex items-center gap-3 flex-1 min-w-0 group cursor-pointer hover:opacity-80 transition-opacity text-left">
              {currentModel ? (
                <>
                  <ModelIcon
                    modelName={currentModel.name}
                    modelId={currentModel.model_id}
                    provider={currentModel.provider}
                    modelIconSlug={currentModel.model_icon_slug}
                    modelIconUrl={currentModel.model_icon_url}
                    providerIconSlug={currentModel.provider_icon_slug}
                    providerIconUrl={currentModel.provider_icon_url}
                    size={28}
                    showTooltip={false}
                    className="flex-shrink-0"
                  />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <p className="text-sm font-medium text-foreground truncate">
                        {removeProviderPrefix(currentModel.name, currentModel.provider)}
                      </p>
                      <ChevronDown className="h-4 w-4 text-muted-foreground flex-shrink-0" />
                    </div>
                    <div className="flex items-center gap-2 mt-0.5">
                      <p className="text-xs text-muted-foreground">
                        {currentModel.provider}
                      </p>
                      <span className="text-muted-foreground/40">•</span>
                      {isSterna ? (
                        <Badge variant="secondary" className="text-xs px-1.5 py-0 h-4">
                          Auto
                        </Badge>
                      ) : isFree ? (
                        <Badge variant="secondary" className="text-xs px-1.5 py-0 h-4">
                          Free
                        </Badge>
                      ) : (
                        <span className="text-xs text-muted-foreground">
                          {pricingUtils.formatCostWithUnit(currentModel.cost_per_1m_prompt)} /
                          {pricingUtils.formatCostWithUnit(currentModel.cost_per_1m_completion)}
                        </span>
                      )}
                    </div>
                  </div>
                </>
              ) : (
                <div className="flex items-center gap-3">
                  <div className="h-7 w-7 rounded-full bg-muted flex items-center justify-center">
                    <RefreshCw className="h-4 w-4 text-muted-foreground" />
                  </div>
                  <div>
                    <p className="text-sm font-medium text-muted-foreground">
                      No model selected
                    </p>
                    <p className="text-xs text-muted-foreground">
                      Click to select a model
                    </p>
                  </div>
                </div>
              )}
            </button>
          </DropdownMenuTrigger>

          <DropdownMenuContent align="start" className="w-80">
            {/* Recent Models */}
            {recentModelsList.length > 0 && (
              <>
                <DropdownMenuLabel className="flex items-center gap-2 text-xs">
                  <Clock className="h-3 w-3" />
                  Recent Models
                </DropdownMenuLabel>
                {recentModelsList.map((model) => (
                  <DropdownMenuItem
                    key={model.id}
                    onClick={() => handleModelSelect(model)}
                    className="flex items-center gap-2 py-2"
                  >
                    <ModelIcon
                      modelName={model.name}
                      modelId={model.model_id}
                      provider={model.provider}
                      modelIconSlug={model.model_icon_slug}
                      modelIconUrl={model.model_icon_url}
                      providerIconSlug={model.provider_icon_slug}
                      providerIconUrl={model.provider_icon_url}
                      size={20}
                      showTooltip={false}
                    />
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium truncate">
                        {removeProviderPrefix(model.name, model.provider)}
                      </p>
                      <p className="text-xs text-muted-foreground">
                        {model.provider}
                      </p>
                    </div>
                  </DropdownMenuItem>
                ))}
                <DropdownMenuSeparator />
              </>
            )}

            {/* Favorite Models */}
            {favoriteModelsList.length > 0 && (
              <>
                <DropdownMenuLabel className="flex items-center gap-2 text-xs">
                  <Star className="h-3 w-3" />
                  Favorites
                </DropdownMenuLabel>
                {favoriteModelsList.map((model) => (
                  <DropdownMenuItem
                    key={model.id}
                    onClick={() => handleModelSelect(model)}
                    className="flex items-center gap-2 py-2"
                  >
                    <ModelIcon
                      modelName={model.name}
                      modelId={model.model_id}
                      provider={model.provider}
                      modelIconSlug={model.model_icon_slug}
                      modelIconUrl={model.model_icon_url}
                      providerIconSlug={model.provider_icon_slug}
                      providerIconUrl={model.provider_icon_url}
                      size={20}
                      showTooltip={false}
                    />
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium truncate">
                        {removeProviderPrefix(model.name, model.provider)}
                      </p>
                      <p className="text-xs text-muted-foreground">
                        {model.provider}
                      </p>
                    </div>
                    <Star className="h-3 w-3 fill-yellow-400 text-yellow-400" />
                  </DropdownMenuItem>
                ))}
                <DropdownMenuSeparator />
              </>
            )}

            {/* Browse All */}
            <DropdownMenuItem
              onClick={onBrowseClick}
              className="flex items-center gap-2 py-2 font-medium"
            >
              <Library className="h-4 w-4" />
              Browse All Models...
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>

        {/* Action Buttons */}
        <div className="flex items-center gap-1 flex-shrink-0">
          {/* Browse Button */}
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={onBrowseClick}
                  className="h-8 w-8"
                >
                  <Library className="h-4 w-4" />
                </Button>
              </TooltipTrigger>
              <TooltipContent>
                <p>Browse All Models</p>
              </TooltipContent>
            </Tooltip>
          </TooltipProvider>

          {/* More menu: actions matching /chats */}
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="icon" title="More options">
                <MoreVertical className="h-4 w-4" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              {/* Stop */}
              {canStop && onStop && (
                <DropdownMenuItem onClick={onStop}>
                  <X className="h-4 w-4 mr-2" /> Stop
                </DropdownMenuItem>
              )}

              {/* Copy/Export */}
              {onCopyResponses && onCopyMetadata && onExportResponses && onExportMetadata && (
                <>
                  <ChatCopyExportItems
                    onCopyResponses={onCopyResponses}
                    onCopyMetadata={onCopyMetadata}
                    onExportResponses={onExportResponses}
                    onExportMetadata={onExportMetadata}
                  />
                  <DropdownMenuSeparator />
                </>
              )}

              {/* Clear chat */}
              {onClearChat && (
                <DropdownMenuItem
                  onClick={onClearChat}
                  disabled={clearDisabled}
                >
                  <Trash2 className="h-4 w-4 mr-2 text-destructive" /> Clear conversation
                </DropdownMenuItem>
              )}
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </div>
    </div>
  )
}
