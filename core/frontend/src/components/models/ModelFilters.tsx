import { useState, useEffect } from 'react'
import { Search, SlidersHorizontal, X, ArrowUpDown, ArrowUp, ArrowDown, ChevronDown } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover'
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from '@/components/ui/sheet'
import { useMediaQuery } from '@/hooks/useMediaQuery'
import { useModelStats } from '@/hooks/useModelStats'
import useModelStore from '@/store/modelStore'
import type { ModelFilter } from '@/types/models'
import { PriceRangeSlider } from './PriceRangeSlider'

export type SortByType = 'none' | 'prompt_cost' | 'completion_cost' | 'overall_cost' | 'max_tokens' | 'provider' | 'latency' | 'throughput'
export type SortOrderType = 'asc' | 'desc'

interface ModelFiltersProps {
  className?: string
  onFilterChange?: (filter: ModelFilter) => void
  onApply?: () => void
  // Sort props
  sortBy?: SortByType
  sortOrder?: SortOrderType
  onSortByChange?: (sortBy: SortByType) => void
  onSortOrderChange?: (order: SortOrderType) => void
}

// Capability definitions for clean iteration
const CAPABILITIES = [
  { key: 'structured_outputs', label: 'JSON' },
  { key: 'reasoning', label: 'Reasoning' },
  { key: 'prompt_caching', label: 'Caching' },
] as const

const MODALITIES = [
  { key: 'image', label: 'Vision' },
  { key: 'audio', label: 'Audio' },
  { key: 'file', label: 'Files' },
] as const

const CONTEXT_OPTIONS = [
  { value: 'all', label: 'Any' },
  { value: '131072', label: '128K+' },
  { value: '200000', label: '200K+' },
  { value: '500000', label: '500K+' },
  { value: '1000000', label: '1M+' },
]

const SORT_OPTIONS: { value: SortByType; label: string }[] = [
  { value: 'none', label: 'Default' },
  { value: 'prompt_cost', label: 'Prompt cost' },
  { value: 'completion_cost', label: 'Completion cost' },
  { value: 'overall_cost', label: 'Overall cost' },
  { value: 'max_tokens', label: 'Context size' },
  { value: 'latency', label: 'Latency' },
  { value: 'throughput', label: 'Throughput' },
]

// Shared filter content for both Sheet and Popover
function FilterContent({
  localFilter,
  handleFilterUpdate,
  toggleCapability,
  toggleModality,
}: {
  localFilter: ModelFilter
  handleFilterUpdate: (updates: Partial<ModelFilter>) => void
  toggleCapability: (key: string) => void
  toggleModality: (modality: string) => void
}) {
  return (
    <>
      {/* Context length */}
      <div className="space-y-2">
        <label className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
          Context window
        </label>
        <div className="flex flex-wrap gap-1.5">
          {CONTEXT_OPTIONS.map(({ value, label }) => {
            const isActive = value === 'all'
              ? !localFilter.minContextLength
              : localFilter.minContextLength?.toString() === value
            return (
              <button
                key={value}
                onClick={() => handleFilterUpdate({
                  minContextLength: value === 'all' ? undefined : parseInt(value)
                })}
                className={cn(
                  "h-7 px-2.5 rounded-md text-xs font-medium transition-all",
                  isActive
                    ? "bg-foreground text-background"
                    : "bg-muted/50 text-muted-foreground hover:bg-muted"
                )}
              >
                {label}
              </button>
            )
          })}
        </div>
      </div>

      {/* Capabilities */}
      <div className="space-y-2">
        <label className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
          Capabilities
        </label>
        <div className="flex flex-wrap gap-1.5">
          {CAPABILITIES.map(({ key, label }) => {
            const isActive = localFilter.capabilities?.[key as keyof typeof localFilter.capabilities] === true
            return (
              <button
                key={key}
                onClick={() => toggleCapability(key)}
                className={cn(
                  "h-7 px-2.5 rounded-md text-xs font-medium transition-all",
                  isActive
                    ? "bg-foreground text-background"
                    : "bg-muted/50 text-muted-foreground hover:bg-muted"
                )}
              >
                {label}
              </button>
            )
          })}
        </div>
      </div>

      {/* Modalities */}
      <div className="space-y-2">
        <label className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
          Input types
        </label>
        <div className="flex flex-wrap gap-1.5">
          {MODALITIES.map(({ key, label }) => {
            const isActive = localFilter.input_modalities?.includes(key)
            return (
              <button
                key={key}
                onClick={() => toggleModality(key)}
                className={cn(
                  "h-7 px-2.5 rounded-md text-xs font-medium transition-all",
                  isActive
                    ? "bg-foreground text-background"
                    : "bg-muted/50 text-muted-foreground hover:bg-muted"
                )}
              >
                {label}
              </button>
            )
          })}
        </div>
      </div>

      {/* Price range */}
      <div className="space-y-2">
        <label className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
          Max price
        </label>
        <PriceRangeSlider
          mode="single"
          value={localFilter.priceRange?.max}
          onChange={(value) => {
            handleFilterUpdate({
              priceRange: value !== undefined ? { min: 0, max: value as number } : undefined
            })
          }}
        />
      </div>

    </>
  )
}

export function ModelFilters({
  className,
  onFilterChange,
  onApply,
  sortBy = 'none',
  sortOrder = 'asc',
  onSortByChange,
  onSortOrderChange,
}: ModelFiltersProps) {
  const { filter, setFilter, clearFilter, fetchModels } = useModelStore()
  const { stats } = useModelStats()
  const [localFilter, setLocalFilter] = useState<ModelFilter>(filter)
  const [searchInput, setSearchInput] = useState(filter.search || '')
  const [moreFiltersOpen, setMoreFiltersOpen] = useState(false)
  const isMobile = useMediaQuery('(max-width: 640px)')

  // Use providers from shared stats hook
  const allProviders = stats.providersList

  useEffect(() => {
    setLocalFilter(filter)
    setSearchInput(filter.search || '')
  }, [filter])

  useEffect(() => {
    const timer = setTimeout(() => {
      if (searchInput !== localFilter.search) {
        const newFilter = { ...localFilter, search: searchInput || undefined }
        setLocalFilter(newFilter)
        setFilter(newFilter)
        fetchModels(1, newFilter)
        onFilterChange?.(newFilter)
      }
    }, 300)
    return () => clearTimeout(timer)
  }, [searchInput, fetchModels])

  const handleFilterUpdate = (updates: Partial<ModelFilter>) => {
    const newFilter = { ...localFilter, ...updates }
    setLocalFilter(newFilter)
    setFilter(newFilter)
    fetchModels(1, newFilter)
    onFilterChange?.(newFilter)
    onApply?.()
  }

  const handleClearFilters = () => {
    setLocalFilter({})
    setSearchInput('')
    clearFilter()
    fetchModels(1, {})
    onFilterChange?.({})
    onApply?.()
  }

  const toggleCapability = (key: string) => {
    const current = localFilter.capabilities?.[key as keyof typeof localFilter.capabilities]
    const newCapabilities = {
      ...localFilter.capabilities,
      [key]: current ? undefined : true,
    }
    // Clean up empty capabilities
    const hasAny = Object.values(newCapabilities).some(v => v === true)
    handleFilterUpdate({ capabilities: hasAny ? newCapabilities : undefined })
  }

  const toggleModality = (modality: string) => {
    const currentModalities = localFilter.input_modalities || []
    const newModalities = currentModalities.includes(modality)
      ? currentModalities.filter(m => m !== modality)
      : [...currentModalities, modality]
    handleFilterUpdate({
      input_modalities: newModalities.length > 0 ? newModalities : undefined
    })
  }

  const hasActiveFilters = () => {
    return !!(
      filter.provider ||
      filter.minContextLength ||
      filter.capabilities?.structured_outputs ||
      filter.capabilities?.reasoning ||
      filter.capabilities?.prompt_caching ||
      (filter.input_modalities && filter.input_modalities.length > 0) ||
      filter.priceRange
    )
  }

  const activeFilterCount = () => {
    let count = 0
    if (filter.provider) count++
    if (filter.minContextLength) count++
    if (filter.capabilities?.structured_outputs) count++
    if (filter.capabilities?.reasoning) count++
    if (filter.capabilities?.prompt_caching) count++
    if (filter.input_modalities?.length) count += filter.input_modalities.length
    if (filter.priceRange) count++
    return count
  }

  const totalActiveCount = activeFilterCount() + (sortBy !== 'none' ? 1 : 0) + (localFilter.provider ? 1 : 0)

  return (
    <div className={cn('space-y-2', className)}>
      {/* Mobile: Search + single filter button */}
      {isMobile ? (
        <div className="flex items-center gap-2">
          <div className="relative flex-1">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground/60" />
            <Input
              placeholder="Search models..."
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              className="h-9 pl-8 pr-8 text-sm bg-muted/30 border-0 focus-visible:ring-1 focus-visible:ring-border"
            />
            {searchInput && (
              <button
                onClick={() => setSearchInput('')}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground/60 hover:text-foreground transition-colors"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            )}
          </div>

          <Sheet open={moreFiltersOpen} onOpenChange={setMoreFiltersOpen}>
            <SheetTrigger asChild>
              <Button
                variant="outline"
                size="sm"
                className="h-9 px-3 gap-2 shrink-0"
              >
                <SlidersHorizontal className="h-4 w-4" />
                {totalActiveCount > 0 && (
                  <span className="flex items-center justify-center h-5 min-w-5 px-1.5 rounded-full bg-foreground text-background text-xs font-semibold">
                    {totalActiveCount}
                  </span>
                )}
              </Button>
            </SheetTrigger>
            <SheetContent side="bottom" className="h-auto max-h-[70vh] rounded-t-2xl p-0 overflow-hidden [&>button]:hidden">
              {/* Header */}
              <div className="flex items-center justify-between px-4 py-3 border-b">
                <SheetTitle className="text-base">Filters</SheetTitle>
                <div className="flex items-center gap-3">
                  {totalActiveCount > 0 && (
                    <button
                      onClick={() => {
                        handleClearFilters()
                        onSortByChange?.('none')
                      }}
                      className="text-sm text-muted-foreground hover:text-foreground"
                    >
                      Reset
                    </button>
                  )}
                  <button
                    onClick={() => setMoreFiltersOpen(false)}
                    className="p-1 -mr-1 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
                  >
                    <X className="h-5 w-5" />
                  </button>
                </div>
              </div>

              <div className="overflow-y-auto overflow-x-hidden max-h-[calc(70vh-56px)]">
                {/* Sort - Compact inline selector */}
                {onSortByChange && (
                  <div className="px-4 py-3 border-b">
                    <div className="flex items-center gap-3">
                      <span className="text-sm text-muted-foreground shrink-0">Sort</span>
                      <div className="flex-1 flex gap-1.5 overflow-x-auto scrollbar-none">
                        {SORT_OPTIONS.map((option) => (
                          <button
                            key={option.value}
                            onClick={() => {
                              if (sortBy === option.value && option.value !== 'none') {
                                // Toggle order if same option clicked
                                onSortOrderChange?.(sortOrder === 'asc' ? 'desc' : 'asc')
                              } else {
                                onSortByChange(option.value)
                              }
                            }}
                            className={cn(
                              "h-7 px-2.5 rounded-md text-xs font-medium whitespace-nowrap transition-all flex items-center gap-1",
                              sortBy === option.value
                                ? "bg-foreground text-background"
                                : "bg-muted/50 text-muted-foreground"
                            )}
                          >
                            {option.label}
                            {sortBy === option.value && option.value !== 'none' && (
                              sortOrder === 'asc' ? <ArrowUp className="h-3 w-3" /> : <ArrowDown className="h-3 w-3" />
                            )}
                          </button>
                        ))}
                      </div>
                    </div>
                  </div>
                )}

                {/* Provider - Horizontal scroll */}
                <div className="px-4 py-3 border-b">
                  <div className="flex items-center gap-3">
                    <span className="text-sm text-muted-foreground shrink-0">Provider</span>
                    <div className="flex-1 flex gap-1.5 overflow-x-auto scrollbar-none">
                      <button
                        onClick={() => handleFilterUpdate({ provider: undefined })}
                        className={cn(
                          "h-7 px-2.5 rounded-md text-xs font-medium whitespace-nowrap transition-all",
                          !localFilter.provider
                            ? "bg-foreground text-background"
                            : "bg-muted/50 text-muted-foreground"
                        )}
                      >
                        All
                      </button>
                      {allProviders.map((provider) => (
                        <button
                          key={provider}
                          onClick={() => handleFilterUpdate({ provider })}
                          className={cn(
                            "h-7 px-2.5 rounded-md text-xs font-medium whitespace-nowrap transition-all",
                            localFilter.provider === provider
                              ? "bg-foreground text-background"
                              : "bg-muted/50 text-muted-foreground"
                          )}
                        >
                          {provider}
                        </button>
                      ))}
                    </div>
                  </div>
                </div>

                {/* Advanced filters - Collapsible */}
                <details className="group">
                  <summary className="px-4 py-3 flex items-center justify-between cursor-pointer list-none border-b">
                    <span className="text-sm text-muted-foreground">More filters</span>
                    <ChevronDown className="h-4 w-4 text-muted-foreground transition-transform group-open:rotate-180" />
                  </summary>
                  <div className="px-4 py-3 space-y-4">
                    <FilterContent
                      localFilter={localFilter}
                      handleFilterUpdate={handleFilterUpdate}
                      toggleCapability={toggleCapability}
                      toggleModality={toggleModality}
                    />
                  </div>
                </details>
              </div>
            </SheetContent>
          </Sheet>
        </div>
      ) : (
        /* Desktop: Compact inline filter bar */
        <div className="flex items-center gap-1.5">
          {/* Search */}
          <div className="relative flex-1 max-w-[200px]">
            <Search className="absolute left-2 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground/50" />
            <Input
              placeholder="Search..."
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              className="h-7 pl-7 pr-7 text-xs bg-transparent border-border/50 focus-visible:ring-1 focus-visible:ring-ring/30"
            />
            {searchInput && (
              <button
                onClick={() => setSearchInput('')}
                className="absolute right-1.5 top-1/2 -translate-y-1/2 p-0.5 rounded text-muted-foreground/50 hover:text-foreground transition-colors"
              >
                <X className="h-3 w-3" />
              </button>
            )}
          </div>

          {/* Provider */}
          <Select
            value={localFilter.provider || 'all'}
            onValueChange={(value) => handleFilterUpdate({ provider: value === 'all' ? undefined : value })}
          >
            <SelectTrigger className="h-7 w-auto min-w-[100px] text-xs border-border/50 bg-transparent gap-1 px-2">
              <SelectValue placeholder="Provider" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all" className="text-xs">All providers</SelectItem>
              {allProviders.map((provider) => (
                <SelectItem key={provider} value={provider} className="text-xs">
                  {provider}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>

          {/* Sort - Combined field + order */}
          {onSortByChange && (
            <Select
              value={sortBy}
              onValueChange={(value) => onSortByChange(value as SortByType)}
            >
              <SelectTrigger className="h-7 w-auto min-w-[90px] text-xs border-border/50 bg-transparent gap-1 px-2">
                {sortBy !== 'none' && onSortOrderChange && (
                  <button
                    onClick={(e) => {
                      e.stopPropagation()
                      onSortOrderChange(sortOrder === 'asc' ? 'desc' : 'asc')
                    }}
                    className="p-0.5 -ml-0.5 rounded hover:bg-muted"
                  >
                    {sortOrder === 'asc' ? (
                      <ArrowUp className="h-3 w-3" />
                    ) : (
                      <ArrowDown className="h-3 w-3" />
                    )}
                  </button>
                )}
                <SelectValue placeholder="Sort" />
              </SelectTrigger>
              <SelectContent>
                {SORT_OPTIONS.map((option) => (
                  <SelectItem key={option.value} value={option.value} className="text-xs">
                    {option.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}

          {/* More Filters */}
          <Popover open={moreFiltersOpen} onOpenChange={setMoreFiltersOpen}>
            <PopoverTrigger asChild>
              <button
                className={cn(
                  "h-7 px-2 flex items-center gap-1 text-xs rounded-md border border-border/50 transition-colors",
                  hasActiveFilters()
                    ? "bg-foreground/5 text-foreground"
                    : "text-muted-foreground hover:text-foreground hover:bg-muted/50"
                )}
              >
                <SlidersHorizontal className="h-3 w-3" />
                {activeFilterCount() > 0 && (
                  <span className="text-[10px] font-medium">{activeFilterCount()}</span>
                )}
              </button>
            </PopoverTrigger>
            <PopoverContent className="w-72 p-3" align="end">
              <div className="flex items-center justify-between mb-3">
                <span className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Filters</span>
                {hasActiveFilters() && (
                  <button
                    onClick={handleClearFilters}
                    className="text-xs text-muted-foreground hover:text-foreground"
                  >
                    Reset
                  </button>
                )}
              </div>
              <div className="space-y-3">
                <FilterContent
                  localFilter={localFilter}
                  handleFilterUpdate={handleFilterUpdate}
                  toggleCapability={toggleCapability}
                  toggleModality={toggleModality}
                />
              </div>
            </PopoverContent>
          </Popover>

          {/* Clear all - only show if filters active */}
          {hasActiveFilters() && (
            <button
              onClick={handleClearFilters}
              className="h-7 px-1.5 text-muted-foreground hover:text-foreground transition-colors"
              title="Clear filters"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          )}
        </div>
      )}
    </div>
  )
}
