import { useEffect, useState, useRef, useCallback, useMemo } from 'react'
import { ArrowUp, ArrowDown } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Badge } from '@/components/ui/badge'
import {
  Pagination,
  PaginationContent,
  PaginationEllipsis,
  PaginationItem,
  PaginationLink,
  PaginationNext,
  PaginationPrevious,
} from '@/components/ui/pagination'
import useModelStore from '@/store/modelStore'
import type { ModelCatalogEntry } from '@/types/models'
import { ModelDetailsModal } from './ModelDetailsModal'
import { ProviderIcon } from './ProviderIcon'
import { MobileModelCard, DesktopModelCard } from './ModelCards'

import type { SortByType, SortOrderType } from './ModelFilters'

interface ModelCatalogBrowserProps {
  onSelectModel?: (model: ModelCatalogEntry) => void
  selectedModelId?: string
  showComparison?: boolean
  className?: string
  // External sort control (optional - if not provided, uses internal state)
  sortBy?: SortByType
  sortOrder?: SortOrderType
  onSortByChange?: (sortBy: SortByType) => void
  onSortOrderChange?: (order: SortOrderType) => void
  // When true, loads all models without pagination (for mobile)
  noPagination?: boolean
}

export type { SortByType, SortOrderType }

export function ModelCatalogBrowser({
  onSelectModel,
  selectedModelId,
  showComparison = true,
  className,
  sortBy: externalSortBy,
  sortOrder: externalSortOrder,
  onSortByChange,
  onSortOrderChange,
  noPagination = false,
}: ModelCatalogBrowserProps) {
  const {
    models,
    loading,
    error,
    filter,
    favorites,
    recentModels,
    fetchModels,
    fetchAllModels,
    allModels,
    allModelsLoading,
    allModelsLoaded,
    addFavorite,
    removeFavorite,
    addToComparison,
    removeFromComparison,
    comparisonModels,
    currentPage,
    totalPages,
    totalCount,
    providerCounts,
    setCurrentPage,
    setCurrentModel,
  } = useModelStore()

  // Use external sort state if provided, otherwise use internal state
  const [internalSortBy, setInternalSortBy] = useState<SortByType>('none')
  const [internalSortOrder, setInternalSortOrder] = useState<SortOrderType>('asc')

  const sortBy = externalSortBy ?? internalSortBy
  const sortOrder = externalSortOrder ?? internalSortOrder
  const setSortBy = onSortByChange ?? setInternalSortBy
  const setSortOrder = onSortOrderChange ?? setInternalSortOrder

  const [detailsModalOpen, setDetailsModalOpen] = useState(false)
  const [selectedModelForDetails, setSelectedModelForDetails] = useState<ModelCatalogEntry | null>(null)

  // Track previous sort values to detect changes
  const prevSortRef = useRef({ sortBy, sortOrder })
  const isFirstMount = useRef(true)

  // Load all models when noPagination is true
  useEffect(() => {
    if (noPagination && !allModelsLoaded && !allModelsLoading) {
      fetchAllModels()
    }
  }, [noPagination, allModelsLoaded, allModelsLoading, fetchAllModels])

  // Load models when page, sort, or filter changes (only when using pagination)
  // Handles page reset on sort change to avoid double-fetch
  useEffect(() => {
    if (noPagination) return

    const filters = {
      ...filter,
      sortBy: sortBy === 'none' ? undefined : sortBy,
      order: sortOrder
    }

    // Check if sort criteria changed
    const sortChanged = prevSortRef.current.sortBy !== sortBy ||
                       prevSortRef.current.sortOrder !== sortOrder
    prevSortRef.current = { sortBy, sortOrder }

    if (isFirstMount.current) {
      isFirstMount.current = false
      fetchModels(1, filters)
    } else if (sortChanged) {
      // When sort changes, reset to page 1 and fetch in one go
      setCurrentPage(1)
      fetchModels(1, filters)
    } else {
      fetchModels(currentPage, filters)
    }
  }, [noPagination, currentPage, sortBy, sortOrder, filter, fetchModels, setCurrentPage])

  // Determine which models to display
  const displayModels = noPagination ? allModels : models
  const isLoading = noPagination ? allModelsLoading : loading

  // Memoized sets for O(1) lookups instead of O(n) array searches
  const favoriteIds = useMemo(() => new Set(favorites.map(f => f.model_id)), [favorites])
  const comparisonIds = useMemo(() => new Set(comparisonModels.map(m => m.model_id)), [comparisonModels])

  // Memoized handlers to prevent unnecessary re-renders
  const handleSelectModel = useCallback((model: ModelCatalogEntry) => {
    setCurrentModel(model)
    onSelectModel?.(model)
  }, [setCurrentModel, onSelectModel])

  const handleViewDetails = useCallback((model: ModelCatalogEntry) => {
    setSelectedModelForDetails(model)
    setDetailsModalOpen(true)
  }, [])

  const handleCloseDetailsModal = useCallback(() => {
    setDetailsModalOpen(false)
    setSelectedModelForDetails(null)
  }, [])

  const toggleFavorite = useCallback((e: React.MouseEvent, modelId: string) => {
    e.stopPropagation()
    if (favoriteIds.has(modelId)) {
      removeFavorite(modelId)
    } else {
      const model = displayModels.find((m) => m.model_id === modelId)
      addFavorite(modelId, model)
    }
  }, [favoriteIds, displayModels, removeFavorite, addFavorite])

  const isInComparison = useCallback((modelId: string) => {
    return comparisonIds.has(modelId)
  }, [comparisonIds])

  // Group models by provider for display when sorting by provider or none
  const groupedByProvider = useMemo(() => {
    if (sortBy !== 'none' && sortBy !== 'provider') return null
    return displayModels.reduce((acc, model) => {
      const provider = model.provider
      if (!acc[provider]) {
        acc[provider] = []
      }
      acc[provider].push(model)
      return acc
    }, {} as Record<string, ModelCatalogEntry[]>)
  }, [sortBy, displayModels])

  // Backend already sorts by icon presence, just preserve order
  const sortedProviderKeys = useMemo(() =>
    groupedByProvider ? Object.keys(groupedByProvider) : []
  , [groupedByProvider])

  // Create card render functions that use the memoized components
  // IMPORTANT: These must be defined before any early returns to follow Rules of Hooks
  const renderMobileCard = useCallback((model: ModelCatalogEntry) => {
    const isFavorite = favoriteIds.has(model.model_id)
    const inComparison = comparisonIds.has(model.model_id)
    const isSelected = selectedModelId === model.model_id

    return (
      <MobileModelCard
        key={model.id}
        model={model}
        isSelected={isSelected}
        isFavorite={isFavorite}
        inComparison={inComparison}
        showComparison={showComparison}
        comparisonCount={comparisonModels.length}
        onViewDetails={() => handleViewDetails(model)}
        onSelect={() => handleSelectModel(model)}
        onToggleFavorite={(e) => toggleFavorite(e, model.model_id)}
        onToggleComparison={(e) => {
          e.stopPropagation()
          if (inComparison) {
            removeFromComparison(model.id)
          } else {
            addToComparison(model)
          }
        }}
      />
    )
  }, [favoriteIds, comparisonIds, selectedModelId, showComparison, comparisonModels.length, handleViewDetails, handleSelectModel, toggleFavorite, removeFromComparison, addToComparison])

  const renderDesktopCard = useCallback((model: ModelCatalogEntry) => {
    const isFavorite = favoriteIds.has(model.model_id)
    const inComparison = comparisonIds.has(model.model_id)
    const isSelected = selectedModelId === model.model_id

    return (
      <DesktopModelCard
        key={model.id}
        model={model}
        isSelected={isSelected}
        isFavorite={isFavorite}
        inComparison={inComparison}
        showComparison={showComparison}
        comparisonCount={comparisonModels.length}
        onViewDetails={() => handleViewDetails(model)}
        onSelect={() => handleSelectModel(model)}
        onToggleFavorite={(e) => toggleFavorite(e, model.model_id)}
        onToggleComparison={(e) => {
          e.stopPropagation()
          if (inComparison) {
            removeFromComparison(model.id)
          } else {
            addToComparison(model)
          }
        }}
      />
    )
  }, [favoriteIds, comparisonIds, selectedModelId, showComparison, comparisonModels.length, handleViewDetails, handleSelectModel, toggleFavorite, removeFromComparison, addToComparison])

  // Early returns for loading/error/empty states
  if (isLoading) {
    return (
      <div className={cn('flex items-center justify-center py-8', className)}>
        <div className="text-muted-foreground">Loading models...</div>
      </div>
    )
  }

  if (error) {
    return (
      <div className={cn('flex items-center justify-center py-8', className)}>
        <div className="text-destructive">{error}</div>
      </div>
    )
  }

  // Check for empty results after filters are applied
  if (!isLoading && displayModels.length === 0) {
    return (
      <div className={cn('flex flex-col items-center justify-center py-12', className)}>
        <div className="text-muted-foreground text-center space-y-2">
          <p className="text-lg font-medium">No models found</p>
          <p className="text-sm">Try adjusting your filters or search criteria</p>
        </div>
      </div>
    )
  }

  return (
    <div className={cn('space-y-4', className)}>
      {/* Models list */}
      {groupedByProvider ? (
        // Grouped by provider view
        <div className="space-y-6">
          {sortedProviderKeys.map(provider => {
            const providerModels = groupedByProvider![provider]
            return (
              <div key={provider} className="space-y-2">
                <h3 className="text-base md:text-lg font-semibold text-foreground border-b pb-2 flex items-center gap-2">
                  <ProviderIcon
                    provider={provider}
                    providerIconSlug={providerModels[0].provider_icon_slug}
                    providerIconUrl={providerModels[0].provider_icon_url}
                    size={20}
                    showTooltip={false}
                  />
                  {provider}
                  <Badge variant="outline" className="text-xs">
                    {providerCounts[provider] || providerModels.length} {(providerCounts[provider] || providerModels.length) === 1 ? 'model' : 'models'}
                  </Badge>
                </h3>
                {/* Mobile list */}
                <div className="md:hidden space-y-2">
                  {providerModels.map(renderMobileCard)}
                </div>
                {/* Desktop grid */}
                <div className="hidden md:grid gap-2">
                  {providerModels.map(renderDesktopCard)}
                </div>
              </div>
            )
          })}
        </div>
      ) : (
        // Standard list view (when sorting)
        <>
          {/* Mobile list */}
          <div className="md:hidden space-y-2">
            {displayModels.map(renderMobileCard)}
          </div>
          {/* Desktop grid */}
          <div className="hidden md:grid gap-2">
            {displayModels.map(renderDesktopCard)}
          </div>
        </>
      )}

      {/* Pagination - hidden when noPagination is true */}
      {!noPagination && totalPages > 1 && (
        <div className="mt-6 flex flex-col items-center gap-2">
          <div className="text-sm text-muted-foreground">
            Showing {((currentPage - 1) * 20) + 1}-{Math.min(currentPage * 20, totalCount)} of {totalCount} models
          </div>
          <Pagination>
            <PaginationContent>
              <PaginationItem>
                <PaginationPrevious
                  onClick={() => {
                    if (currentPage > 1) {
                      setCurrentPage(currentPage - 1)
                    }
                  }}
                  className={cn(
                    'cursor-pointer',
                    currentPage === 1 && 'pointer-events-none opacity-50'
                  )}
                />
              </PaginationItem>

              {/* Page numbers - simplified on mobile */}
              <div className="hidden md:contents">
                {(() => {
                  const pageNumbers = []
                  const maxVisible = 5
                  let startPage = Math.max(1, currentPage - 2)
                  let endPage = Math.min(totalPages, startPage + maxVisible - 1)

                  if (endPage - startPage < maxVisible - 1) {
                    startPage = Math.max(1, endPage - maxVisible + 1)
                  }

                  if (startPage > 1) {
                    pageNumbers.push(
                      <PaginationItem key={1}>
                        <PaginationLink
                          onClick={() => setCurrentPage(1)}
                          isActive={currentPage === 1}
                          className="cursor-pointer"
                        >
                          1
                        </PaginationLink>
                      </PaginationItem>
                    )
                    if (startPage > 2) {
                      pageNumbers.push(
                        <PaginationItem key="ellipsis1">
                          <PaginationEllipsis />
                        </PaginationItem>
                      )
                    }
                  }

                  for (let i = startPage; i <= endPage; i++) {
                    pageNumbers.push(
                      <PaginationItem key={i}>
                        <PaginationLink
                          onClick={() => setCurrentPage(i)}
                          isActive={currentPage === i}
                          className="cursor-pointer"
                        >
                          {i}
                        </PaginationLink>
                      </PaginationItem>
                    )
                  }

                  if (endPage < totalPages) {
                    if (endPage < totalPages - 1) {
                      pageNumbers.push(
                        <PaginationItem key="ellipsis2">
                          <PaginationEllipsis />
                        </PaginationItem>
                      )
                    }
                    pageNumbers.push(
                      <PaginationItem key={totalPages}>
                        <PaginationLink
                          onClick={() => setCurrentPage(totalPages)}
                          isActive={currentPage === totalPages}
                          className="cursor-pointer"
                        >
                          {totalPages}
                        </PaginationLink>
                      </PaginationItem>
                    )
                  }

                  return pageNumbers
                })()}
              </div>

              {/* Mobile: simple page indicator */}
              <PaginationItem className="md:hidden">
                <span className="px-3 py-2 text-sm">
                  {currentPage} / {totalPages}
                </span>
              </PaginationItem>

              <PaginationItem>
                <PaginationNext
                  onClick={() => {
                    if (currentPage < totalPages) {
                      setCurrentPage(currentPage + 1)
                    }
                  }}
                  className={cn(
                    'cursor-pointer',
                    currentPage === totalPages && 'pointer-events-none opacity-50'
                  )}
                />
              </PaginationItem>
            </PaginationContent>
          </Pagination>
        </div>
      )}

      {/* Model Details Modal */}
      <ModelDetailsModal
        isOpen={detailsModalOpen}
        onClose={handleCloseDetailsModal}
        model={selectedModelForDetails}
        onSelectModel={handleSelectModel}
        selectedModelId={selectedModelId}
      />
    </div>
  )
}
