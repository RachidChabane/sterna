import { memo } from 'react'
import { Star, Check, Plus, Clock, Zap } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Card } from '@/components/ui/card'
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import type { ModelCatalogEntry } from '@/types/models'
import { ModelIcon } from './ModelIcon'
import { ModelCapabilitiesBadges } from './ModelCapabilitiesBadges'
import { pricingUtils } from '@/lib/pricing-utils'
import { removeProviderPrefix, isModelNew } from '@/lib/model-utils'

interface MobileModelCardProps {
  model: ModelCatalogEntry
  isSelected: boolean
  isFavorite: boolean
  inComparison: boolean
  showComparison: boolean
  comparisonCount: number
  onViewDetails: () => void
  onSelect: () => void
  onToggleFavorite: (e: React.MouseEvent) => void
  onToggleComparison: (e: React.MouseEvent) => void
}

export const MobileModelCard = memo(function MobileModelCard({
  model,
  isSelected,
  isFavorite,
  inComparison,
  showComparison,
  comparisonCount,
  onViewDetails,
  onSelect,
  onToggleFavorite,
  onToggleComparison,
}: MobileModelCardProps) {
  return (
    <div
      className={cn(
        'flex items-center gap-3 p-3 rounded-lg border bg-card cursor-pointer transition-colors',
        'active:bg-secondary',
        isSelected && 'ring-2 ring-inset ring-accent-brand bg-accent-brand/5'
      )}
      onClick={onViewDetails}
    >
      {/* Model Icon */}
      <ModelIcon
        modelName={model.name}
        modelId={model.model_id}
        provider={model.provider}
        modelIconSlug={model.model_icon_slug}
        modelIconUrl={model.model_icon_url}
        providerIconSlug={model.provider_icon_slug}
        providerIconUrl={model.provider_icon_url}
        size={32}
        showTooltip={false}
      />

      {/* Model Info */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-1.5">
          <h4 className="font-medium text-sm truncate">
            {removeProviderPrefix(model.name, model.provider)}
          </h4>
          {isModelNew(model.first_seen_at) && (
            <Badge className="text-[10px] h-4 px-1 bg-accent-brand text-white flex-shrink-0">
              New
            </Badge>
          )}
        </div>
        <div className="flex items-center gap-2 mt-0.5 flex-wrap">
          <span className="text-xs text-muted-foreground">
            {model.model_id === 'ornithops/sterna' ? 'Auto' : pricingUtils.formatCostWithUnit(model.cost_per_1m_prompt)}
          </span>
          <span className="text-muted-foreground/30">•</span>
          <span className="text-xs text-muted-foreground">
            {(model.max_tokens / 1000).toFixed(0)}K ctx
          </span>
          {model.latency_p50 != null && (
            <>
              <span className="text-muted-foreground/30">•</span>
              <span className="text-xs text-muted-foreground flex items-center gap-0.5">
                <Clock className="h-3 w-3" />
                {model.latency_p50}ms
              </span>
            </>
          )}
          {model.throughput_p50 != null && (
            <>
              <span className="text-muted-foreground/30">•</span>
              <span className="text-xs text-muted-foreground flex items-center gap-0.5">
                <Zap className="h-3 w-3" />
                {model.throughput_p50.toFixed(0)}tok/s
              </span>
            </>
          )}
        </div>
      </div>

      {/* Action buttons */}
      <div className="flex items-center gap-1 flex-shrink-0">
        <Button
          size="icon"
          variant="ghost"
          className="h-8 w-8"
          onClick={onToggleFavorite}
        >
          <Star
            className={cn(
              'h-4 w-4',
              isFavorite
                ? 'fill-yellow-500 text-yellow-500'
                : 'text-muted-foreground'
            )}
          />
        </Button>
        <Button
          size="icon"
          variant={isSelected ? 'default' : 'ghost'}
          className={cn(
            'h-8 w-8',
            isSelected && 'bg-accent-brand hover:bg-accent-brand/90 text-white'
          )}
          onClick={(e) => {
            e.stopPropagation()
            onSelect()
          }}
        >
          <Check className="h-4 w-4" />
        </Button>
        {showComparison && (
          <Button
            size="icon"
            variant={inComparison ? 'default' : 'ghost'}
            className="h-8 w-8"
            onClick={onToggleComparison}
            disabled={!inComparison && comparisonCount >= 5}
          >
            <Plus className={cn('h-4 w-4', inComparison && 'rotate-45')} />
          </Button>
        )}
      </div>
    </div>
  )
}, (prevProps, nextProps) => {
  // Custom comparison - only re-render if these specific props change
  return (
    prevProps.model.model_id === nextProps.model.model_id &&
    prevProps.isSelected === nextProps.isSelected &&
    prevProps.isFavorite === nextProps.isFavorite &&
    prevProps.inComparison === nextProps.inComparison &&
    prevProps.showComparison === nextProps.showComparison &&
    prevProps.comparisonCount === nextProps.comparisonCount
  )
})

interface DesktopModelCardProps {
  model: ModelCatalogEntry
  isSelected: boolean
  isFavorite: boolean
  inComparison: boolean
  showComparison: boolean
  comparisonCount: number
  onViewDetails: () => void
  onSelect: () => void
  onToggleFavorite: (e: React.MouseEvent) => void
  onToggleComparison: (e: React.MouseEvent) => void
}

export const DesktopModelCard = memo(function DesktopModelCard({
  model,
  isSelected,
  isFavorite,
  inComparison,
  showComparison,
  comparisonCount,
  onViewDetails,
  onSelect,
  onToggleFavorite,
  onToggleComparison,
}: DesktopModelCardProps) {
  return (
    <TooltipProvider>
      <Card
        className={cn(
          'p-4 hover:bg-secondary hover:text-foreground cursor-pointer transition-colors',
          isSelected && 'ring-2 ring-inset ring-accent-brand'
        )}
        onClick={onViewDetails}
      >
        <div className="flex items-start justify-between gap-4">
        <div className="flex-1 space-y-2">
          <div className="flex items-start gap-2">
            <div className="flex-1">
              <div className="flex items-center gap-2">
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
                <h4 className="font-medium">{removeProviderPrefix(model.name, model.provider)}</h4>
                {isModelNew(model.first_seen_at) && (
                  <Badge className="text-xs h-4 px-1 bg-accent-brand text-white">
                    New
                  </Badge>
                )}
                {isSelected && (
                  <Badge variant="outline" className="text-xs">
                    <Check className="h-3 w-3 mr-1" />
                    Selected
                  </Badge>
                )}
              </div>
              <p className="text-sm text-muted-foreground">
                {model.model_id}
              </p>
            </div>
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  size="icon"
                  variant="ghost"
                  className="h-8 w-8"
                  onClick={onToggleFavorite}
                >
                  <Star
                    className={cn(
                      'h-4 w-4',
                      isFavorite
                        ? 'fill-yellow-500 text-yellow-500'
                        : 'text-muted-foreground'
                    )}
                  />
                </Button>
              </TooltipTrigger>
              <TooltipContent>
                {isFavorite ? 'Remove from favorites' : 'Add to favorites'}
              </TooltipContent>
            </Tooltip>
          </div>

          <div className="flex flex-wrap gap-2">
            {/* Cost badges */}
            {model.model_id === 'ornithops/sterna' ? (
              <Badge variant="outline" className="text-xs bg-background/50">
                Auto-routing
              </Badge>
            ) : (
              <>
                <Badge variant="outline" className="text-xs bg-background/50">
                  Prompt: {pricingUtils.formatCostWithUnit(model.cost_per_1m_prompt)}
                </Badge>
                <Badge variant="outline" className="text-xs bg-background/50">
                  Completion: {pricingUtils.formatCostWithUnit(model.cost_per_1m_completion)}
                </Badge>
              </>
            )}

            {/* Capabilities */}
            <ModelCapabilitiesBadges model={model} displayMode="badge" />

            {/* Max tokens */}
            <Badge variant="outline" className="text-xs bg-background/50">
              Max: {model.max_tokens.toLocaleString()} tokens
            </Badge>

            {/* Performance stats */}
            {model.latency_p50 != null && (
              <Badge variant="outline" className="text-xs bg-background/50">
                <Clock className="h-3 w-3 mr-1" />
                {model.latency_p50.toLocaleString()} ms
              </Badge>
            )}
            {model.throughput_p50 != null && (
              <Badge variant="outline" className="text-xs bg-background/50">
                <Zap className="h-3 w-3 mr-1" />
                {model.throughput_p50.toFixed(1)} tok/s
              </Badge>
            )}
          </div>

          {/* Tags */}
          {model.tags.length > 0 && (
            <div className="flex flex-wrap gap-1">
              {model.tags.map((tag) => (
                <Badge
                  key={tag}
                  variant="outline"
                  className="text-xs bg-background/50"
                >
                  {tag}
                </Badge>
              ))}
            </div>
          )}
        </div>

        {/* Actions */}
        <div className="flex items-start gap-2">
          {/* Select button */}
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                size="sm"
                variant={isSelected ? 'default' : 'outline'}
                onClick={(e) => {
                  e.stopPropagation()
                  onSelect()
                }}
                className={cn(
                  isSelected && 'bg-accent-brand hover:bg-accent-brand/90 text-white'
                )}
              >
                {isSelected ? (
                  <>
                    <Check className="h-4 w-4 mr-1" />
                    Selected
                  </>
                ) : (
                  <>
                    <Check className="h-4 w-4 mr-1" />
                    Select
                  </>
                )}
              </Button>
            </TooltipTrigger>
            <TooltipContent>
              {isSelected ? 'Currently selected model' : 'Select this model'}
            </TooltipContent>
          </Tooltip>

          {/* Compare button */}
          {showComparison && (
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  size="sm"
                  variant={inComparison ? 'default' : 'outline'}
                  onClick={onToggleComparison}
                  disabled={!inComparison && comparisonCount >= 5}
                >
                  {inComparison ? (
                    <>
                      <Check className="h-4 w-4 mr-1" />
                      In Comparison
                    </>
                  ) : (
                    <>
                      <Plus className="h-4 w-4 mr-1" />
                      Compare
                    </>
                  )}
                </Button>
              </TooltipTrigger>
              <TooltipContent>
                {inComparison
                  ? 'Remove from comparison'
                  : comparisonCount >= 5
                    ? 'Maximum 5 models can be compared'
                    : 'Add to comparison'
                }
              </TooltipContent>
            </Tooltip>
          )}
        </div>
      </div>
      </Card>
    </TooltipProvider>
  )
}, (prevProps, nextProps) => {
  // Custom comparison - only re-render if these specific props change
  return (
    prevProps.model.model_id === nextProps.model.model_id &&
    prevProps.isSelected === nextProps.isSelected &&
    prevProps.isFavorite === nextProps.isFavorite &&
    prevProps.inComparison === nextProps.inComparison &&
    prevProps.showComparison === nextProps.showComparison &&
    prevProps.comparisonCount === nextProps.comparisonCount
  )
})
