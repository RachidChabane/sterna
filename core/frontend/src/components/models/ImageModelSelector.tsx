import { useState, useEffect } from 'react'
import { Image, ChevronDown, Star, Zap, Type, Camera, Sparkles, RefreshCw } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
  DropdownMenuGroup,
} from '@/components/ui/dropdown-menu'
import { ProviderIcon } from '@/components/models/ProviderIcon'
import useImageModelStore from '@/store/imageModelStore'
import { cn } from '@/lib/utils'
import { isModelNew } from '@/lib/model-utils'
import type { ImageModelCatalogEntry } from '@/types/models'
import { Badge } from '@/components/ui/badge'

interface ImageModelSelectorProps {
  className?: string
  compact?: boolean
}

export function ImageModelSelector({ className, compact = false }: ImageModelSelectorProps) {
  const {
    models,
    currentModel,
    favorites,
    loading,
    fetchModels,
    setCurrentModel
  } = useImageModelStore()
  const [isOpen, setIsOpen] = useState(false)

  // Fetch models on mount if not already loaded
  useEffect(() => {
    if (models.length === 0 && !loading) {
      fetchModels()
    }
  }, [models.length, loading, fetchModels])

  const handleModelSelect = (model: ImageModelCatalogEntry) => {
    setCurrentModel(model)
    setIsOpen(false)
  }

  // Get favorite models with details
  const getFavoriteModels = () => {
    return favorites
      .map((fav) => fav.details || models.find((m) => m.model_id === fav.model_id))
      .filter((m): m is ImageModelCatalogEntry => m !== undefined)
      .slice(0, 5)
  }

  const favoriteModels = getFavoriteModels()

  // Group models by provider
  const groupedModels = models.reduce((acc, model) => {
    if (!acc[model.provider]) {
      acc[model.provider] = []
    }
    acc[model.provider].push(model)
    return acc
  }, {} as Record<string, ImageModelCatalogEntry[]>)

  // Format price for display
  const formatPrice = (price: number | null) => {
    if (price === null) return 'N/A'
    if (price < 0.01) return `$${(price * 100).toFixed(1)}c`
    return `$${price.toFixed(2)}`
  }

  // Get capability badges for a model
  const getModelBadges = (model: ImageModelCatalogEntry) => {
    const badges = []
    if (model.is_fast) badges.push({ icon: Zap, label: 'Fast', color: 'text-yellow-500' })
    if (model.best_for_text) badges.push({ icon: Type, label: 'Text', color: 'text-blue-500' })
    if (model.best_for_photorealism) badges.push({ icon: Camera, label: 'Photo', color: 'text-green-500' })
    if (isModelNew(model.first_seen_at)) badges.push({ icon: Sparkles, label: 'New', color: 'text-purple-500' })
    return badges
  }

  const ModelItem = ({ model }: { model: ImageModelCatalogEntry }) => {
    const badges = getModelBadges(model)
    const isFavorite = favorites.some((f) => f.model_id === model.model_id)

    return (
      <DropdownMenuItem
        className="flex items-start gap-2 py-2 cursor-pointer"
        onClick={() => handleModelSelect(model)}
      >
        <ProviderIcon
          provider={model.provider}
          providerIconSlug={model.provider_icon_slug}
          providerIconUrl={model.provider_icon_url}
          size={16}
          showTooltip={false}
          className="mt-0.5 flex-shrink-0"
        />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1.5">
            <span className="text-sm font-medium truncate">{model.name}</span>
            {isFavorite && <Star className="h-3 w-3 text-yellow-500 fill-yellow-500 flex-shrink-0" />}
          </div>
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <span>{formatPrice(model.price_per_image)}/img</span>
            {badges.slice(0, 2).map((badge, idx) => (
              <badge.icon key={idx} className={cn("h-3 w-3", badge.color)} />
            ))}
          </div>
        </div>
      </DropdownMenuItem>
    )
  }

  return (
    <DropdownMenu open={isOpen} onOpenChange={setIsOpen}>
      <DropdownMenuTrigger asChild>
        <Button
          variant="outline"
          className={cn(
            "w-full justify-between gap-2",
            currentModel && "border-accent-purple/40 hover:border-accent-purple",
            className
          )}
        >
          {currentModel ? (
            <ProviderIcon
              provider={currentModel.provider}
              providerIconSlug={currentModel.provider_icon_slug}
              providerIconUrl={currentModel.provider_icon_url}
              size={16}
              showTooltip={false}
              className="flex-shrink-0"
            />
          ) : (
            <Image className="h-4 w-4 text-accent-purple flex-shrink-0" />
          )}
          {!compact && (
            <span className="flex-1 min-w-0 truncate text-left text-sm">
              {currentModel ? currentModel.name : 'Select Image Model'}
            </span>
          )}
          <ChevronDown className="h-4 w-4 opacity-50 flex-shrink-0" />
        </Button>
      </DropdownMenuTrigger>

      <DropdownMenuContent className="w-80" align="end">
        {/* Current Model */}
        {currentModel ? (
          <>
            <DropdownMenuLabel>Current Image Model</DropdownMenuLabel>
            <div className="px-2 py-2 bg-accent-purple/10 border border-accent-purple/30 rounded-md mx-2">
              <div className="flex items-start gap-2">
                <ProviderIcon
                  provider={currentModel.provider}
                  providerIconSlug={currentModel.provider_icon_slug}
                  providerIconUrl={currentModel.provider_icon_url}
                  size={20}
                  showTooltip={false}
                  className="mt-0.5 flex-shrink-0"
                />
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-foreground truncate">
                    {currentModel.name}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {currentModel.provider} - {formatPrice(currentModel.price_per_image)}/image
                  </p>
                  <div className="flex flex-wrap gap-1 mt-1">
                    {getModelBadges(currentModel).map((badge, idx) => (
                      <Badge key={idx} variant="secondary" className="text-xs py-0 px-1.5">
                        <badge.icon className={cn("h-2.5 w-2.5 mr-0.5", badge.color)} />
                        {badge.label}
                      </Badge>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          </>
        ) : (
          <>
            <DropdownMenuLabel>No Image Model Selected</DropdownMenuLabel>
            <div className="px-2 py-2 mx-2">
              <p className="text-xs text-muted-foreground">
                Select an image generation model to enable image creation
              </p>
            </div>
          </>
        )}

        {/* Favorites */}
        {favoriteModels.length > 0 && (
          <>
            <DropdownMenuSeparator />
            <DropdownMenuLabel className="flex items-center gap-1.5">
              <Star className="h-3 w-3 text-yellow-500 fill-yellow-500" />
              Favorites
            </DropdownMenuLabel>
            <DropdownMenuGroup>
              {favoriteModels.map((model) => (
                <ModelItem key={model.model_id} model={model} />
              ))}
            </DropdownMenuGroup>
          </>
        )}

        {/* All Models by Provider */}
        <DropdownMenuSeparator />
        <DropdownMenuLabel>All Models</DropdownMenuLabel>

        {loading ? (
          <div className="flex items-center justify-center py-4">
            <RefreshCw className="h-4 w-4 animate-spin text-muted-foreground" />
            <span className="ml-2 text-sm text-muted-foreground">Loading models...</span>
          </div>
        ) : Object.keys(groupedModels).length === 0 ? (
          <div className="px-2 py-4 text-center text-sm text-muted-foreground">
            No image models available
          </div>
        ) : (
          Object.entries(groupedModels).map(([provider, providerModels]) => (
            <DropdownMenuGroup key={provider}>
              <DropdownMenuLabel className="text-xs text-muted-foreground font-normal capitalize">
                {provider}
              </DropdownMenuLabel>
              {providerModels.map((model) => (
                <ModelItem key={model.model_id} model={model} />
              ))}
            </DropdownMenuGroup>
          ))
        )}

        {/* Footer */}
        <DropdownMenuSeparator />
        <div className="p-2 text-center">
          <p className="text-xs text-muted-foreground">
            {models.length} models available from {Object.keys(groupedModels).length} providers
          </p>
        </div>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

export default ImageModelSelector
