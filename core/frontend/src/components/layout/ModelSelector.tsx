import { useState } from 'react'
import { Brain, ChevronDown, Star, ChevronUp } from 'lucide-react'
import { useNavigate, useRouterState } from '@tanstack/react-router'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { ModelIcon } from '@/components/models/ModelIcon'
import { ProviderIcon } from '@/components/models/ProviderIcon'
import useModelStore from '@/store/modelStore'
import type { ModelCatalogEntry } from '@/types/models'
import { cn } from '@/lib/utils'
import { removeProviderPrefix } from '@/lib/model-utils'

interface ModelSelectorProps {
  /** Override the current model (defaults to global store) */
  currentModel?: ModelCatalogEntry | null
  /** Custom handler for model selection (defaults to global setCurrentModel) */
  onModelSelect?: (model: ModelCatalogEntry) => void
  /** Variant for different layouts */
  variant?: 'default' | 'compact'
  /** Custom class name for the trigger button */
  className?: string
  /** Alignment for the dropdown */
  align?: 'start' | 'end' | 'center'
}

export function ModelSelector({
  currentModel: propCurrentModel,
  onModelSelect: propOnModelSelect,
  variant = 'default',
  className,
  align = 'end',
}: ModelSelectorProps = {}) {
  const navigate = useNavigate()
  const routerState = useRouterState()
  const pathname = routerState.location.pathname
  const { currentModel: storeCurrentModel, recentModels, models, setCurrentModel, favorites } = useModelStore()
  const [expandedSection, setExpandedSection] = useState<'favorites' | 'recent' | null>('favorites')

  // Use prop values if provided, otherwise fall back to store
  const currentModel = propCurrentModel !== undefined ? propCurrentModel : storeCurrentModel
  const handleModelSelectInternal = propOnModelSelect || setCurrentModel

  // Get full model details for recent models
  const getRecentModelDetails = () => {
    return recentModels
      .slice(0, 5)
      .map((recent) => {
        // Use stored details if available, otherwise search in models array (for backward compatibility)
        return recent.details || models.find((m) => m.model_id === recent.model_id)
      })
      .filter((m) => m !== undefined)
      .slice(0, 5)
  }

  const recentModelDetails = getRecentModelDetails()

  // Get full model details for favorite models
  const getFavoriteModelDetails = () => {
    return favorites
      .slice(0, 5)
      .map((fav) => fav.details || models.find((m) => m.model_id === fav.model_id))
      .filter((m) => m !== undefined)
  }

  const favoriteModelDetails = getFavoriteModelDetails()

  const handleModelSelect = (model: ModelCatalogEntry) => {
    handleModelSelectInternal(model)
  }

  const handleBrowseModels = () => {
    navigate({ to: '/models' })
  }

  // Truncate long model names
  const truncateName = (name: string, maxLength: number = 20) => {
    return name.length > maxLength ? `${name.substring(0, maxLength)}...` : name
  }

  const isCompact = variant === 'compact'

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        {isCompact ? (
          <button
            className={cn(
              "flex items-center gap-1.5 px-2 py-1 rounded bg-muted/30 hover:bg-muted/50 text-xs transition-colors",
              className
            )}
          >
            {currentModel ? (
              <ModelIcon
                modelName={currentModel.name}
                modelId={currentModel.model_id}
                provider={currentModel.provider}
                modelIconSlug={currentModel.model_icon_slug}
                modelIconUrl={currentModel.model_icon_url}
                providerIconSlug={currentModel.provider_icon_slug}
                providerIconUrl={currentModel.provider_icon_url}
                size={14}
                showTooltip={false}
              />
            ) : (
              <Brain className="h-3.5 w-3.5 flex-shrink-0" />
            )}
            <span className="truncate max-w-[120px]">
              {currentModel ? removeProviderPrefix(currentModel.name, currentModel.provider) : 'Model'}
            </span>
            <ChevronDown className="h-3 w-3 opacity-50 flex-shrink-0" />
          </button>
        ) : (
          <Button
            variant="outline"
            className={cn(
              "w-full justify-between gap-2",
              currentModel && "border-accent-brand/40 hover:border-accent-brand",
              className
            )}
          >
            {currentModel ? (
              <ModelIcon
                modelName={currentModel.name}
                modelId={currentModel.model_id}
                provider={currentModel.provider}
                modelIconSlug={currentModel.model_icon_slug}
                modelIconUrl={currentModel.model_icon_url}
                providerIconSlug={currentModel.provider_icon_slug}
                providerIconUrl={currentModel.provider_icon_url}
                size={16}
                showTooltip={false}
                className="flex-shrink-0"
              />
            ) : (
              <Brain className="h-4 w-4 text-accent-brand flex-shrink-0" />
            )}
            <span className="flex-1 min-w-0 truncate text-left text-sm">
              {currentModel ? truncateName(removeProviderPrefix(currentModel.name, currentModel.provider)) : 'Select Model'}
            </span>
            <ChevronDown className="h-4 w-4 opacity-50 flex-shrink-0" />
          </Button>
        )}
      </DropdownMenuTrigger>
      <DropdownMenuContent className="w-72" align={align}>
        {currentModel ? (
          <>
            <DropdownMenuLabel>Current Model</DropdownMenuLabel>
            <div className="px-2 py-2 bg-accent-brand/10 border border-accent-brand rounded-md mx-2">
              <div className="flex items-start gap-2">
                <ModelIcon
                  modelName={currentModel.name}
                  modelId={currentModel.model_id}
                  provider={currentModel.provider}
                  modelIconSlug={currentModel.model_icon_slug}
                  modelIconUrl={currentModel.model_icon_url}
                  providerIconSlug={currentModel.provider_icon_slug}
                  providerIconUrl={currentModel.provider_icon_url}
                  size={16}
                  showTooltip={false}
                  className="mt-0.5 flex-shrink-0"
                />
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-foreground truncate">
                    {removeProviderPrefix(currentModel.name, currentModel.provider)}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {currentModel.provider}
                  </p>
                </div>
              </div>
            </div>
          </>
        ) : (
          <>
            <DropdownMenuLabel>No Model Selected</DropdownMenuLabel>
            <div className="px-2 py-2 mx-2">
              <p className="text-xs text-muted-foreground">
                Select a model from the catalog to get started
              </p>
            </div>
          </>
        )}

        {favoriteModelDetails.length > 0 && (
          <>
            <DropdownMenuSeparator />
            <div
              className="flex items-center justify-between px-2 py-1.5 cursor-pointer hover:bg-secondary/50 rounded-md transition-colors mx-2"
              onClick={() => setExpandedSection(expandedSection === 'favorites' ? null : 'favorites')}
            >
              <div className="flex items-center gap-1.5 text-xs text-muted-foreground font-normal">
                <Star className="h-3 w-3 text-yellow-500 fill-yellow-500" />
                Favorite Models
              </div>
              {expandedSection === 'favorites' ? (
                <ChevronUp className="h-3 w-3 text-muted-foreground" />
              ) : (
                <ChevronDown className="h-3 w-3 text-muted-foreground" />
              )}
            </div>
            <div
              className={cn(
                "overflow-hidden transition-all duration-300 ease-in-out",
                expandedSection === 'favorites' ? "max-h-[500px] opacity-100" : "max-h-0 opacity-0 pointer-events-none"
              )}
            >
              {favoriteModelDetails.map((model) => (
                <DropdownMenuItem
                  key={model.model_id}
                  onClick={() => handleModelSelect(model)}
                  className={cn(
                    "cursor-pointer",
                    currentModel?.model_id === model.model_id && "bg-secondary"
                  )}
                >
                  <div className="flex items-start gap-2 flex-1 min-w-0">
                    <div className="relative flex-shrink-0">
                      <ModelIcon
                        modelName={model.name}
                        modelId={model.model_id}
                        provider={model.provider}
                        modelIconSlug={model.model_icon_slug}
                        modelIconUrl={model.model_icon_url}
                        providerIconSlug={model.provider_icon_slug}
                        providerIconUrl={model.provider_icon_url}
                        size={16}
                        showTooltip={false}
                        className="mt-0.5"
                      />
                    </div>
                    <div className="flex flex-col gap-0.5 flex-1 min-w-0">
                      <span className="text-sm truncate">{removeProviderPrefix(model.name, model.provider)}</span>
                      <span className="text-xs text-muted-foreground">{model.provider}</span>
                    </div>
                  </div>
                </DropdownMenuItem>
              ))}
            </div>
          </>
        )}

        {recentModelDetails.length > 0 && (
          <>
            <DropdownMenuSeparator />
            <div
              className="flex items-center justify-between px-2 py-1.5 cursor-pointer hover:bg-secondary/50 rounded-md transition-colors mx-2"
              onClick={() => setExpandedSection(expandedSection === 'recent' ? null : 'recent')}
            >
              <span className="text-xs text-muted-foreground font-normal">Recent Models</span>
              {expandedSection === 'recent' ? (
                <ChevronUp className="h-3 w-3 text-muted-foreground" />
              ) : (
                <ChevronDown className="h-3 w-3 text-muted-foreground" />
              )}
            </div>
            <div
              className={cn(
                "overflow-hidden transition-all duration-300 ease-in-out",
                expandedSection === 'recent' ? "max-h-[500px] opacity-100" : "max-h-0 opacity-0 pointer-events-none"
              )}
            >
              {recentModelDetails.map((model) => (
                <DropdownMenuItem
                  key={model.model_id}
                  onClick={() => handleModelSelect(model)}
                  className={cn(
                    "cursor-pointer",
                    currentModel?.model_id === model.model_id && "bg-secondary"
                  )}
                >
                  <div className="flex items-start gap-2 flex-1 min-w-0">
                    <ModelIcon
                      modelName={model.name}
                      modelId={model.model_id}
                      provider={model.provider}
                      modelIconSlug={model.model_icon_slug}
                      modelIconUrl={model.model_icon_url}
                      providerIconSlug={model.provider_icon_slug}
                      providerIconUrl={model.provider_icon_url}
                      size={16}
                      showTooltip={false}
                      className="mt-0.5 flex-shrink-0"
                    />
                    <div className="flex flex-col gap-0.5 flex-1 min-w-0">
                      <span className="text-sm truncate">{removeProviderPrefix(model.name, model.provider)}</span>
                      <span className="text-xs text-muted-foreground">{model.provider}</span>
                    </div>
                  </div>
                </DropdownMenuItem>
              ))}
            </div>
          </>
        )}

        {pathname !== '/models' && (
          <>
            <DropdownMenuSeparator />
            <div className="p-2">
              <Button
                onClick={handleBrowseModels}
                className="w-full bg-accent-brand text-white hover:bg-accent-brand/90 hover:shadow-glow-brand transition-all"
                size="sm"
              >
                Browse Models →
              </Button>
            </div>
          </>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
