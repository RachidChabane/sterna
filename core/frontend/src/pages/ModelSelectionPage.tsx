import { useState, useEffect, useMemo, useCallback } from 'react'
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from '@/components/ui/tabs'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import {
  Alert,
  AlertDescription,
  AlertTitle,
} from '@/components/ui/alert'
import {
  DollarSign,
  GitCompare,
  Star,
  Info,
  Package,
  X,
  Check,
  Search,
} from 'lucide-react'
import { PremiumMenuIcon } from '@/components/ui/premium-menu-icon'
import { ModelCatalogBrowser } from '@/components/models/ModelCatalogBrowser'
import { ModelFilters, type SortByType, type SortOrderType } from '@/components/models/ModelFilters'
import { ModelComparisonMatrix } from '@/components/models/ModelComparisonMatrix'
import { CostCalculator } from '@/components/models/CostCalculator'
import { MobileModelComparison } from '@/components/models/MobileModelComparison'
import { MobileCostCalculator } from '@/components/models/MobileCostCalculator'
import { ModelIcon } from '@/components/models/ModelIcon'
import { ProviderIcon } from '@/components/models/ProviderIcon'
import { FavoriteModelsModal } from '@/components/models/FavoriteModelsModal'
import useModelStore from '@/store/modelStore'
import { useNavigationStore } from '@/store/navigationStore'
import { useToast } from '@/hooks/use-toast'
import { useModelStats } from '@/hooks/useModelStats'
import type { ModelCatalogEntry } from '@/types/models'
import { pricingUtils } from '@/lib/pricing-utils'
import { removeProviderPrefix } from '@/lib/model-utils'
import { cn } from '@/lib/utils'

export function ModelSelectionPage() {
  const {
    models,
    error,
    favorites,
    recentModels,
    comparisonModels,
    currentModel,
    setCurrentModel,
    clearComparison,
    removeFavorite,
  } = useModelStore()
  const { toast } = useToast()
  const { openMobileSidebar } = useNavigationStore()
  const { stats: modelStats } = useModelStats()
  const [selectedTab, setSelectedTab] = useState('catalog')
  const [isFavoritesModalOpen, setIsFavoritesModalOpen] = useState(false)
  const [sortBy, setSortBy] = useState<SortByType>('none')
  const [sortOrder, setSortOrder] = useState<SortOrderType>('asc')

  const handleModelSelect = useCallback((model: ModelCatalogEntry) => {
    setCurrentModel(model)
  }, [setCurrentModel])

  // Memoize favorite models to avoid O(n*m) recalculation on every render
  const favoriteModels = useMemo(() => {
    // Create a map of models for O(1) lookup
    const modelsMap = new Map(models.map(m => [m.model_id, m]))
    return favorites
      .map((fav) => fav.details || modelsMap.get(fav.model_id))
      .filter((m): m is ModelCatalogEntry => m !== undefined)
  }, [favorites, models])

  return (
    <>
      {/* ========== MOBILE LAYOUT ========== */}
      <div className="md:hidden flex flex-col h-full overflow-hidden">
        {/* Mobile Header - Compact stats */}
        <div className="px-3 py-2 border-b bg-background/95 backdrop-blur flex-shrink-0">
          <div className="flex items-center gap-2">
            {/* Menu button */}
            <Button
              variant="ghost"
              size="sm"
              className="h-8 w-8 p-0 shrink-0"
              onClick={openMobileSidebar}
            >
              <PremiumMenuIcon size={18} />
            </Button>

            <div className="flex items-center gap-2 text-xs text-muted-foreground flex-1">
              <span className="font-medium text-foreground">{modelStats.total}</span> models
              <span className="text-muted-foreground/30">•</span>
              <span className="font-medium text-foreground">{modelStats.providers}</span> providers
            </div>
            <div className="flex items-center gap-2">
              {favorites.length > 0 && (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setIsFavoritesModalOpen(true)}
                  className="h-8 px-2 gap-1"
                >
                  <Star className="h-3.5 w-3.5 text-yellow-500 fill-yellow-500" />
                  <span className="text-xs">{favorites.length}</span>
                </Button>
              )}
              {comparisonModels.length > 0 && (
                <Badge variant="secondary" className="h-6 gap-1">
                  <GitCompare className="h-3 w-3" />
                  {comparisonModels.length}
                </Badge>
              )}
            </div>
          </div>
        </div>

        {/* Mobile Quick Access - Selected Model Banner */}
        {currentModel && (
          <div className="px-4 py-2 bg-accent-brand/10 border-b border-accent-brand/30 flex-shrink-0">
            <div className="flex items-center gap-2">
              <Check className="h-4 w-4 text-accent-brand flex-shrink-0" />
              <ModelIcon
                modelName={currentModel.name}
                modelId={currentModel.model_id}
                provider={currentModel.provider}
                modelIconSlug={currentModel.model_icon_slug}
                modelIconUrl={currentModel.model_icon_url}
                providerIconSlug={currentModel.provider_icon_slug}
                providerIconUrl={currentModel.provider_icon_url}
                size={20}
                showTooltip={false}
              />
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium truncate">
                  {removeProviderPrefix(currentModel.name, currentModel.provider)}
                </p>
              </div>
              <Badge variant="outline" className="text-xs h-5 flex-shrink-0">
                {pricingUtils.formatCostWithUnit(currentModel.cost_per_1m_prompt)}
              </Badge>
            </div>
          </div>
        )}

        {/* Mobile Favorites Strip */}
        {favorites.length > 0 && (
          <div className="px-4 py-2 border-b bg-muted/30 flex-shrink-0">
            <div className="flex items-center gap-2 overflow-x-auto scrollbar-hide pb-1">
              <Star className="h-3.5 w-3.5 text-yellow-500 fill-yellow-500 flex-shrink-0" />
              {favoriteModels.slice(0, 6).map((model) => {
                const isSelected = currentModel?.model_id === model.model_id
                return (
                  <button
                    key={model.id}
                    onClick={() => handleModelSelect(model)}
                    className={cn(
                      "flex items-center gap-1.5 px-2 py-1 rounded-full border transition-colors flex-shrink-0",
                      isSelected
                        ? "bg-accent-brand/20 border-accent-brand"
                        : "bg-background border-border hover:border-accent-brand/50"
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
                      size={16}
                      showTooltip={false}
                    />
                    <span className="text-xs font-medium max-w-[80px] truncate">
                      {removeProviderPrefix(model.name, model.provider).split(' ')[0]}
                    </span>
                  </button>
                )
              })}
              {favorites.length > 6 && (
                <button
                  onClick={() => setIsFavoritesModalOpen(true)}
                  className="text-xs text-muted-foreground hover:text-foreground flex-shrink-0"
                >
                  +{favorites.length - 6}
                </button>
              )}
            </div>
          </div>
        )}

        {/* Mobile Tabs */}
        <Tabs value={selectedTab} onValueChange={setSelectedTab} className="flex-1 flex flex-col min-h-0">
          <div className="px-4 py-2 border-b bg-background sticky top-0 z-10 flex-shrink-0">
            <TabsList className="w-full h-9">
              <TabsTrigger value="catalog" className="flex-1 text-xs gap-1 h-7">
                <Search className="h-3.5 w-3.5" />
                Browse
              </TabsTrigger>
              <TabsTrigger value="compare" className="flex-1 text-xs gap-1 h-7">
                <GitCompare className="h-3.5 w-3.5" />
                Compare
                {comparisonModels.length > 0 && (
                  <Badge className="ml-0.5 h-4 min-w-4 px-1 text-[10px] bg-accent-brand flex items-center justify-center">
                    {comparisonModels.length}
                  </Badge>
                )}
              </TabsTrigger>
              <TabsTrigger value="calculator" className="flex-1 text-xs gap-1 h-7">
                <DollarSign className="h-3.5 w-3.5" />
                Cost
              </TabsTrigger>
            </TabsList>
          </div>

          <TabsContent value="catalog" className="mt-0 flex-1 overflow-hidden data-[state=active]:flex data-[state=active]:flex-col data-[state=inactive]:hidden">
            {/* Mobile Search & Filters - sticky */}
            <div className="px-4 py-2 border-b bg-background flex-shrink-0">
              <ModelFilters
                sortBy={sortBy}
                sortOrder={sortOrder}
                onSortByChange={setSortBy}
                onSortOrderChange={setSortOrder}
              />
            </div>
            {/* Mobile Model List - only this scrolls */}
            <div className="flex-1 overflow-y-auto min-h-0 px-4 py-2">
              {error && (
                <Alert variant="destructive" className="mb-4">
                  <AlertTitle>Error loading models</AlertTitle>
                  <AlertDescription>{error}</AlertDescription>
                </Alert>
              )}
              <ModelCatalogBrowser
                onSelectModel={handleModelSelect}
                selectedModelId={currentModel?.model_id}
                className="mobile-compact"
                sortBy={sortBy}
                sortOrder={sortOrder}
                onSortByChange={setSortBy}
                onSortOrderChange={setSortOrder}
              />
            </div>
          </TabsContent>

          <TabsContent value="compare" className="mt-0 flex-1 overflow-hidden data-[state=active]:flex data-[state=active]:flex-col data-[state=inactive]:hidden">
            <div className="flex-1 overflow-y-auto min-h-0 px-4 py-4">
              <MobileModelComparison />
            </div>
          </TabsContent>

          <TabsContent value="calculator" className="mt-0 flex-1 overflow-hidden data-[state=active]:flex data-[state=active]:flex-col data-[state=inactive]:hidden">
            <div className="flex-1 overflow-y-auto min-h-0 px-4 py-4">
              <MobileCostCalculator
                selectedModel={currentModel || undefined}
                onModelSelect={handleModelSelect}
              />
            </div>
          </TabsContent>
        </Tabs>
      </div>

      {/* ========== DESKTOP LAYOUT ========== */}
      <div className="hidden md:flex md:flex-col md:h-full px-6 py-6 space-y-6 overflow-hidden">
        {/* Minimal stats bar */}
        <div className="flex items-center justify-between text-sm text-muted-foreground">
          <div className="flex items-center gap-4">
            <span>{modelStats.total} models</span>
            <span className="text-muted-foreground/50">•</span>
            <span>{modelStats.providers} providers</span>
            {comparisonModels.length > 0 && (
              <>
                <span className="text-muted-foreground/50">•</span>
                <span className="flex items-center gap-1.5">
                  {comparisonModels.length} in comparison
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={clearComparison}
                    className="h-5 px-1.5 text-xs text-muted-foreground hover:text-foreground"
                  >
                    Clear
                  </Button>
                </span>
              </>
            )}
          </div>
          {favorites.length > 0 && (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setIsFavoritesModalOpen(true)}
              className="h-7 text-xs gap-1.5"
            >
              <Star className="h-3.5 w-3.5 text-yellow-500" />
              {favorites.length} favorites
            </Button>
          )}
        </div>

        {/* Quick access section */}
        {(favorites.length > 0 || recentModels.length > 0 || currentModel) && (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 items-start">
            {favorites.length > 0 && (
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2 text-lg">
                    <Star className="h-5 w-5 text-yellow-500" />
                    Favorite Models
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="grid grid-cols-3 gap-3">
                    {favoriteModels
                      .slice(0, 2)
                      .map((model) => {
                        const isSelected = currentModel?.model_id === model.model_id

                        return (
                          <div
                            key={model.id}
                            className={cn(
                              "group relative p-3 rounded-lg border-2 transition-all cursor-pointer",
                              "hover:shadow-lg hover:scale-[1.02] hover:border-accent-brand/50",
                              isSelected
                                ? "bg-accent-brand/10 border-accent-brand shadow-md"
                                : "bg-background/50 border-border hover:bg-secondary/50"
                            )}
                            onClick={() => handleModelSelect(model)}
                          >
                            <div className="flex items-start gap-2">
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
                                <div className="flex items-center gap-1">
                                  <h4 className="font-medium text-sm truncate">
                                    {removeProviderPrefix(model.name, model.provider)}
                                  </h4>
                                  {isSelected && (
                                    <Check className="h-3 w-3 text-accent-brand flex-shrink-0" />
                                  )}
                                </div>
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
                                <div className="mt-1 text-xs text-muted-foreground">
                                  {pricingUtils.formatCostWithUnit(model.cost_per_1m_prompt)}
                                </div>
                              </div>

                              {/* Remove Button (visible on hover) */}
                              <Button
                                size="icon"
                                variant="ghost"
                                className="h-6 w-6 opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0"
                                onClick={(e) => {
                                  e.stopPropagation()
                                  removeFavorite(model.model_id)
                                  toast({
                                    title: "Removed from favorites",
                                    description: `${model.name} has been removed from your favorites.`,
                                  })
                                }}
                              >
                                <X className="h-3 w-3" />
                              </Button>
                            </div>
                          </div>
                        )
                      })}

                    {/* Show "X more" card if there are more than 2 favorites */}
                    {favorites.length > 2 && (
                      <div
                        className="flex items-center justify-center p-3 rounded-lg border-2 border-dashed border-border bg-secondary/30 cursor-pointer hover:bg-secondary/50 transition-colors"
                        onClick={() => setIsFavoritesModalOpen(true)}
                      >
                        <div className="text-center">
                          <span className="text-sm font-medium text-muted-foreground">
                            +{favorites.length - 2} more
                          </span>
                          <p className="text-xs text-muted-foreground mt-1">
                            Manage favorites
                          </p>
                        </div>
                      </div>
                    )}
                  </div>
                </CardContent>
              </Card>
            )}

            {/* Selected Model Display */}
            {currentModel && (
              <Card className="bg-accent-brand/10 border-2 border-accent-brand h-full">
                <CardHeader>
                  <CardTitle className="flex items-center gap-2 text-lg">
                    <Check className="h-5 w-5 text-accent-brand" />
                    Selected Model
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="p-3 rounded-lg border-2 border-accent-brand bg-background/50">
                    <div className="flex items-start gap-2">
                      {/* Model Icon */}
                      <div className="flex-shrink-0">
                        <ModelIcon
                          modelName={currentModel.name}
                          modelId={currentModel.model_id}
                          provider={currentModel.provider}
                          modelIconSlug={currentModel.model_icon_slug}
                          modelIconUrl={currentModel.model_icon_url}
                          providerIconSlug={currentModel.provider_icon_slug}
                          providerIconUrl={currentModel.provider_icon_url}
                          size={24}
                          showTooltip={false}
                        />
                      </div>

                      {/* Model Info */}
                      <div className="flex-1 min-w-0">
                        <h4 className="font-medium text-sm truncate">
                          {removeProviderPrefix(currentModel.name, currentModel.provider)}
                        </h4>
                        <div className="flex items-center gap-1.5 mt-0.5">
                          <ProviderIcon
                            provider={currentModel.provider}
                            providerIconSlug={currentModel.provider_icon_slug}
                            providerIconUrl={currentModel.provider_icon_url}
                            size={12}
                            showTooltip={false}
                          />
                          <span className="text-xs text-muted-foreground truncate">
                            {currentModel.provider}
                          </span>
                        </div>
                        <div className="mt-1 flex flex-wrap gap-2 text-xs text-muted-foreground">
                          <span>{pricingUtils.formatCostWithUnit(currentModel.cost_per_1m_prompt)}</span>
                          {currentModel.max_tokens && (
                            <span>{currentModel.max_tokens.toLocaleString()} ctx</span>
                          )}
                        </div>
                      </div>
                    </div>
                  </div>
                </CardContent>
              </Card>
            )}
          </div>
        )}

        {/* Main content tabs */}
        <Tabs value={selectedTab} onValueChange={setSelectedTab} className="flex-1 flex flex-col min-h-0">
          <TabsList className="grid w-full grid-cols-3 flex-shrink-0">
            <TabsTrigger value="catalog" className="flex items-center gap-2">
              <Package className="h-4 w-4" />
              Catalog
            </TabsTrigger>
            <TabsTrigger value="compare" className="flex items-center gap-2">
              <GitCompare className="h-4 w-4" />
              Compare
              {comparisonModels.length > 0 && (
                <Badge className="ml-1 h-5 bg-accent-brand text-white rounded-full px-1.5 py-0 text-xs font-medium">
                  {comparisonModels.length}
                </Badge>
              )}
            </TabsTrigger>
            <TabsTrigger value="calculator" className="flex items-center gap-2">
              <DollarSign className="h-4 w-4" />
              Calculator
            </TabsTrigger>
          </TabsList>

          <TabsContent value="catalog" className="flex-1 flex flex-col min-h-0 pt-4 space-y-4 data-[state=inactive]:hidden">
            <div className="flex-shrink-0">
              <ModelFilters
                sortBy={sortBy}
                sortOrder={sortOrder}
                onSortByChange={setSortBy}
                onSortOrderChange={setSortOrder}
              />
            </div>

            {error && (
              <Alert variant="destructive" className="flex-shrink-0">
                <AlertTitle>Error loading models</AlertTitle>
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            )}
            <div className="flex-1 overflow-y-auto min-h-0">
              <ModelCatalogBrowser
                onSelectModel={handleModelSelect}
                selectedModelId={currentModel?.model_id}
                sortBy={sortBy}
                sortOrder={sortOrder}
                onSortByChange={setSortBy}
                onSortOrderChange={setSortOrder}
              />
            </div>
          </TabsContent>

          <TabsContent value="compare" className="flex-1 overflow-y-auto min-h-0 pt-4 space-y-4 data-[state=inactive]:hidden">
            {comparisonModels.length === 0 ? (
              <Alert>
                <Info className="h-4 w-4" />
                <AlertTitle>No models selected</AlertTitle>
                <AlertDescription>
                  Add models from the catalog to compare their features and costs.
                  You can compare up to 5 models at once.
                </AlertDescription>
              </Alert>
            ) : (
              <ModelComparisonMatrix />
            )}
          </TabsContent>

          <TabsContent value="calculator" className="flex-1 overflow-y-auto min-h-0 pt-4 data-[state=inactive]:hidden">
            <CostCalculator
              selectedModel={currentModel || undefined}
              onModelSelect={handleModelSelect}
            />
          </TabsContent>
        </Tabs>
      </div>

      {/* Favorite Models Modal */}
      <FavoriteModelsModal
        open={isFavoritesModalOpen}
        onOpenChange={setIsFavoritesModalOpen}
      />
    </>
  )
}
