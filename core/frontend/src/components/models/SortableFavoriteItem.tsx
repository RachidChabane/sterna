import { useSortable } from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import { GripVertical, X, DollarSign } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { ModelIcon } from './ModelIcon'
import { ProviderIcon } from './ProviderIcon'
import type { ModelCatalogEntry } from '@/types/models'
import { removeProviderPrefix } from '@/lib/model-utils'
import { pricingUtils } from '@/lib/pricing-utils'

interface SortableFavoriteItemProps {
  model: ModelCatalogEntry
  onRemove: (modelId: string) => void
  onModelClick?: (model: ModelCatalogEntry) => void
  isCurrentModel?: boolean
}

export function SortableFavoriteItem({ model, onRemove, onModelClick, isCurrentModel }: SortableFavoriteItemProps) {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: model.model_id })

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
  }

  const costLevel =
    model.cost_per_1m_prompt < 0.5 ? 'low' :
    model.cost_per_1m_prompt < 5 ? 'medium' : 'high'

  return (
    <div
      ref={setNodeRef}
      style={style}
      className={cn(
        "relative group cursor-grab hover:cursor-grab active:cursor-grabbing",
        isDragging && "z-50 opacity-50"
      )}
    >
      <div className="relative">
        <div
          className="flex items-center gap-3 p-3 rounded-lg border-2 border-border bg-background hover:bg-secondary/50 transition-colors cursor-pointer"
          onClick={() => onModelClick?.(model)}
        >
          {/* Drag Handle */}
          <div
            {...attributes}
            {...listeners}
            className="cursor-grab active:cursor-grabbing flex-shrink-0 text-muted-foreground hover:text-foreground transition-colors"
            onClick={(e) => e.stopPropagation()}
          >
            <GripVertical className="h-5 w-5" />
          </div>

          {/* Model Icon */}
          <div className="flex-shrink-0">
            <ModelIcon
              modelName={model.name}
              modelId={model.model_id}
              provider={model.provider}
              modelIconSlug={model.model_icon_slug}
              modelIconUrl={model.model_icon_url}
              providerIconSlug={model.provider_icon_slug}
              providerIconUrl={model.provider_icon_url}
              size={24}
              showTooltip={false}
            />
          </div>

          {/* Model Info */}
          <div className="flex-1 min-w-0">
            <h4 className="font-medium text-sm truncate">
              {removeProviderPrefix(model.name, model.provider)}
            </h4>
            <div className="flex items-center gap-1.5 mt-0.5">
              <ProviderIcon
                provider={model.provider}
                providerIconSlug={model.provider_icon_slug}
                providerIconUrl={model.provider_icon_url}
                size={12}
                showTooltip={false}
              />
              <span className="text-xs text-muted-foreground truncate">
                {model.provider}
              </span>
            </div>
          </div>

          {/* Cost Badge */}
          <Badge
            variant="outline"
            className={cn(
              "text-xs h-5 flex-shrink-0 max-w-[120px] truncate",
              costLevel === 'low' && "border-green-500/30 text-green-600 bg-green-50/50 dark:bg-green-950/20",
              costLevel === 'medium' && "border-yellow-500/30 text-yellow-600 bg-yellow-50/50 dark:bg-yellow-950/20",
              costLevel === 'high' && "border-red-500/30 text-red-600 bg-red-50/50 dark:bg-red-950/20"
            )}
          >
            {pricingUtils.formatCostWithUnit(model.cost_per_1m_prompt)}
          </Badge>

          {/* Spacer for remove button */}
          <div className="w-8 flex-shrink-0" />
        </div>

        {/* Remove Button - positioned absolutely, hidden for current model */}
        {!isCurrentModel && (
          <Button
            size="icon"
            variant="ghost"
            className="absolute top-2 right-2 h-8 w-8 opacity-0 group-hover:opacity-100 transition-opacity z-10 pointer-events-auto"
            onClick={(e) => {
              e.stopPropagation()
              e.preventDefault()
              onRemove(model.model_id)
            }}
            onPointerDown={(e) => {
              e.stopPropagation()
            }}
          >
            <X className="h-4 w-4" />
          </Button>
        )}
      </div>
    </div>
  )
}
