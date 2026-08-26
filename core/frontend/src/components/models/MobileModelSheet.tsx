import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { cn } from '@/lib/utils'
import { removeProviderPrefix } from '@/lib/model-utils'
import { pricingUtils } from '@/lib/pricing-utils'
import { ModelIcon } from './ModelIcon'
import type { Model } from './types'
import type { ModelCatalogEntry } from '@/types/models'

interface MobileModelSheetProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  models: ModelCatalogEntry[]
  selectedModelId?: string
  onSelectModel: (model: Model) => void
}

export function MobileModelSheet({ open, onOpenChange, models, selectedModelId, onSelectModel }: MobileModelSheetProps) {
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="bottom" className="h-[70vh] rounded-t-xl">
        <SheetHeader className="pt-2 pb-4">
          <SheetTitle>Select a model</SheetTitle>
        </SheetHeader>
        <div className="overflow-y-auto h-[calc(100%-4rem)] -mx-6 px-6">
          <div className="space-y-1">
            {models.map((model) => {
              const isSelected = model.model_id === selectedModelId
              return (
                <button
                  key={model.model_id}
                  onClick={() => {
                    onSelectModel(model as Model)
                    onOpenChange(false)
                  }}
                  className={cn(
                    "w-full flex items-center gap-3 p-3 rounded-lg text-left transition-colors",
                    isSelected
                      ? "bg-accent text-accent-foreground"
                      : "hover:bg-muted"
                  )}
                >
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
                  <div className="flex-1 min-w-0">
                    <div className="font-medium truncate text-sm">{removeProviderPrefix(model.name, model.provider)}</div>
                    <div className="text-xs text-muted-foreground truncate">{model.provider}</div>
                  </div>
                  <div className="text-right flex-shrink-0">
                    <div className="text-xs text-muted-foreground">
                      {pricingUtils.formatCostWithUnit((model.cost_per_1m_prompt + model.cost_per_1m_completion) / 2)}
                    </div>
                  </div>
                  {isSelected && (
                    <div className="w-2 h-2 rounded-full bg-primary flex-shrink-0" />
                  )}
                </button>
              )
            })}
          </div>
        </div>
      </SheetContent>
    </Sheet>
  )
}
