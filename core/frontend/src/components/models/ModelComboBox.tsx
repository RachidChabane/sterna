import { memo, useMemo, useCallback } from 'react'
import { SimpleCombobox, type SimpleComboboxOption } from "@/components/ui/simple-combobox"
import { Label } from "@/components/ui/label"
import { Code, Braces, Brain, Camera, Database } from "lucide-react"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import useModelStore from '@/store/modelStore'
import { useTheme } from '@/hooks/useTheme'
import { PriceRangeSlider } from './PriceRangeSlider'
import { ProviderSelect } from './ProviderSelect'
import { ModelIcon } from './ModelIcon'
import { ProviderIcon } from './ProviderIcon'
import type { Model, Filters } from './types'
import { toModelCatalogEntry } from './modelCatalog'
import { pricingUtils } from '@/lib/pricing-utils'
import { removeProviderPrefix, isModelNew } from '@/lib/model-utils'

interface ModelComboBoxProps {
  models: Model[]
  value?: string
  onValueChange: (modelId: string) => void
  disabled?: boolean
  className?: string
  /** Placeholder text shown when no model is selected */
  placeholder?: string
  showFilters?: boolean
  onToggleFilters?: () => void
  hasActiveFilters?: boolean
  filters?: Filters
  onFiltersChange?: (filters: Filters) => void
  providers?: string[]
  recentModelIds?: string[]
  /** Compact mode - show only icon in trigger button */
  compact?: boolean
  /** Hide the chevron icon in the trigger button */
  hideChevron?: boolean
  /** Button variant for the trigger */
  variant?: "default" | "outline" | "ghost" | "secondary"
}

// Memoize to prevent re-rendering entire model list when parent updates
// Critical: prevents renderOption from being called 100+ times on every keystroke
export const ModelComboBox = memo(function ModelComboBox({
  models,
  value,
  onValueChange,
  disabled,
  className,
  placeholder = "Select a model...",
  showFilters,
  onToggleFilters,
  hasActiveFilters,
  filters = {},
  onFiltersChange,
  providers = [],
  recentModelIds = [],
  compact = false,
  hideChevron = false,
  variant = "outline",
}: ModelComboBoxProps) {
  const { favorites, addFavorite, removeFavorite } = useModelStore()
  const { isDark } = useTheme() // Used to trigger icon re-render on theme change

  const clearFilters = useCallback(() => {
    if (onFiltersChange) {
      onFiltersChange({})
    }
  }, [onFiltersChange])

  // Memoize callback to prevent breaking SimpleCombobox memo
  const handleToggleFavorite = useCallback((modelId: string, isFavorite: boolean) => {
    if (isFavorite) {
      const model = models.find((m) => m.model_id === modelId)
      addFavorite(modelId, model ? toModelCatalogEntry(model) : undefined)
    } else {
      removeFavorite(modelId)
    }
  }, [models, addFavorite, removeFavorite])

  // Filter models based on filters prop
  const filteredModels = useMemo(() => {
    return models.filter(model => {
      // Provider filter
      if (filters.provider && model.provider !== filters.provider) {
        return false
      }
      // Max price filter (comparing prompt price in $/1M tokens)
      if (filters.maxPrice !== undefined && model.cost_per_1m_prompt !== null) {
        if (model.cost_per_1m_prompt > filters.maxPrice) {
          return false
        }
      }
      // Min context filter
      if (filters.minContext !== undefined && model.max_tokens < filters.minContext) {
        return false
      }
      // Functions/Tools support filter
      if (filters.supportsFunctions !== undefined && model.supports_functions !== filters.supportsFunctions) {
        return false
      }
      // Structured outputs support filter
      if (filters.supportsStructuredOutputs !== undefined && model.supports_structured_outputs !== filters.supportsStructuredOutputs) {
        return false
      }
      // Reasoning support filter
      if (filters.supportsReasoning !== undefined && model.supports_reasoning !== filters.supportsReasoning) {
        return false
      }
      // Prompt caching support filter
      if (filters.supportsPromptCaching !== undefined && model.supports_prompt_caching !== filters.supportsPromptCaching) {
        return false
      }
      // Input modalities filter (vision, audio, etc.)
      if (filters.input_modalities && filters.input_modalities.length > 0) {
        for (const modality of filters.input_modalities) {
          if (!model.input_modalities?.includes(modality)) {
            return false
          }
        }
      }
      return true
    })
  }, [models, filters])

  // Memoize options to prevent re-creating on every render
  // Critical: prevents SimpleCombobox from re-rendering when parent updates
  const options: SimpleComboboxOption[] = useMemo(() => filteredModels.map((model) => ({
    value: model.model_id,
    label: removeProviderPrefix(model.name, model.provider),
    group: model.provider,
    description: formatModelDescription(model),
    // Compute is_new client-side based on first_seen_at to avoid stale cached values
    metadata: { ...model, is_new: isModelNew(model.first_seen_at) },
    isFavorite: favorites.some(f => f.model_id === model.model_id),
    icon: (
      <ModelIcon
        modelName={model.name}
        modelId={model.model_id}
        provider={model.provider}
        modelIconSlug={model.model_icon_slug}
        modelIconUrl={model.model_icon_url}
        providerIconSlug={model.provider_icon_slug}
        providerIconUrl={model.provider_icon_url}
        size={18}
        showTooltip={false}
      />
    ),
    groupIcon: (
      <ProviderIcon
        provider={model.provider}
        providerIconSlug={model.provider_icon_slug}
        providerIconUrl={model.provider_icon_url}
        size={14}
        showTooltip={false}
      />
    ),
  // isDark dependency ensures icons re-render when theme changes (for adaptive colors)
  })), [filteredModels, favorites, isDark])

  // Memoize sorted options
  const sortedOptions = useMemo(() => [...options].sort((a, b) => {
    // Favorites come first
    if (a.isFavorite !== b.isFavorite) {
      return a.isFavorite ? -1 : 1
    }
    // Then by provider
    if (a.group !== b.group) {
      return (a.group || "").localeCompare(b.group || "")
    }
    // Finally by name
    return a.label.localeCompare(b.label)
  }), [options])

  // Memoize filter content to prevent re-creating callbacks on every render
  const filterContent = useMemo(() => onFiltersChange && (
    <div className="space-y-2.5">
      {/* Row 1: Provider + Context in a 2-column grid */}
      <div className="grid grid-cols-2 gap-2">
        <div className="space-y-1">
          <Label className="text-[10px] font-medium text-muted-foreground uppercase tracking-wide">Provider</Label>
          <ProviderSelect
            providers={providers}
            value={filters.provider || undefined}
            onValueChange={(value) => onFiltersChange({ ...filters, provider: value || '' })}
            size="sm"
          />
        </div>
        <div className="space-y-1">
          <Label className="text-[10px] font-medium text-muted-foreground uppercase tracking-wide">Context</Label>
          <Select
            value={filters.minContext?.toString() || 'all'}
            onValueChange={(value) =>
              onFiltersChange({
                ...filters,
                minContext: value === 'all' ? undefined : value ? parseInt(value) : undefined
              })
            }
          >
            <SelectTrigger className="h-8 text-xs">
              <SelectValue placeholder="Any" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all" className="text-xs">Any</SelectItem>
              <SelectItem value="8192" className="text-xs">8K+</SelectItem>
              <SelectItem value="32768" className="text-xs">32K+</SelectItem>
              <SelectItem value="65536" className="text-xs">64K+</SelectItem>
              <SelectItem value="131072" className="text-xs">128K+</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>

      {/* Row 2: Max price slider */}
      <PriceRangeSlider
        mode="single"
        value={filters.maxPrice}
        onChange={(value) => {
          onFiltersChange({
            ...filters,
            maxPrice: value as number | undefined
          })
        }}
      />

      {/* Row 3: Capabilities as compact toggle chips in 3-column grid */}
      <div className="space-y-1">
        <Label className="text-[10px] font-medium text-muted-foreground uppercase tracking-wide">Capabilities</Label>
        <div className="grid grid-cols-3 gap-1">
          {/* Tools */}
          <button
            type="button"
            onClick={() => onFiltersChange({
              ...filters,
              supportsFunctions: filters.supportsFunctions ? undefined : true
            })}
            className={`flex items-center justify-center gap-1 px-1.5 py-1 text-[10px] rounded border transition-colors ${
              filters.supportsFunctions
                ? 'bg-foreground/10 border-foreground/20 text-foreground'
                : 'bg-transparent border-border/50 text-muted-foreground hover:border-border hover:text-foreground'
            }`}
          >
            <Code className="h-2.5 w-2.5" />
            Tools
          </button>
          {/* Structured */}
          <button
            type="button"
            onClick={() => onFiltersChange({
              ...filters,
              supportsStructuredOutputs: filters.supportsStructuredOutputs ? undefined : true
            })}
            className={`flex items-center justify-center gap-1 px-1.5 py-1 text-[10px] rounded border transition-colors ${
              filters.supportsStructuredOutputs
                ? 'bg-foreground/10 border-foreground/20 text-foreground'
                : 'bg-transparent border-border/50 text-muted-foreground hover:border-border hover:text-foreground'
            }`}
          >
            <Braces className="h-2.5 w-2.5" />
            JSON
          </button>
          {/* Reasoning */}
          <button
            type="button"
            onClick={() => onFiltersChange({
              ...filters,
              supportsReasoning: filters.supportsReasoning ? undefined : true
            })}
            className={`flex items-center justify-center gap-1 px-1.5 py-1 text-[10px] rounded border transition-colors ${
              filters.supportsReasoning
                ? 'bg-foreground/10 border-foreground/20 text-foreground'
                : 'bg-transparent border-border/50 text-muted-foreground hover:border-border hover:text-foreground'
            }`}
          >
            <Brain className="h-2.5 w-2.5" />
            Reasoning
          </button>
          {/* Vision */}
          <button
            type="button"
            onClick={() => {
              const currentModalities = filters.input_modalities || []
              const hasImage = currentModalities.includes('image')
              const newModalities = hasImage
                ? currentModalities.filter(m => m !== 'image')
                : [...currentModalities, 'image']
              onFiltersChange({
                ...filters,
                input_modalities: newModalities.length > 0 ? newModalities : undefined
              })
            }}
            className={`flex items-center justify-center gap-1 px-1.5 py-1 text-[10px] rounded border transition-colors ${
              filters.input_modalities?.includes('image')
                ? 'bg-foreground/10 border-foreground/20 text-foreground'
                : 'bg-transparent border-border/50 text-muted-foreground hover:border-border hover:text-foreground'
            }`}
          >
            <Camera className="h-2.5 w-2.5" />
            Vision
          </button>
          {/* Caching */}
          <button
            type="button"
            onClick={() => onFiltersChange({
              ...filters,
              supportsPromptCaching: filters.supportsPromptCaching ? undefined : true
            })}
            className={`flex items-center justify-center gap-1 px-1.5 py-1 text-[10px] rounded border transition-colors ${
              filters.supportsPromptCaching
                ? 'bg-foreground/10 border-foreground/20 text-foreground'
                : 'bg-transparent border-border/50 text-muted-foreground hover:border-border hover:text-foreground'
            }`}
          >
            <Database className="h-2.5 w-2.5" />
            Cache
          </button>
        </div>
      </div>

      {/* Clear filters - only show if active */}
      {hasActiveFilters && (
        <button
          type="button"
          onClick={clearFilters}
          className="w-full text-[10px] text-muted-foreground hover:text-foreground py-1 transition-colors"
        >
          Clear all filters
        </button>
      )}
    </div>
  ), [onFiltersChange, providers, filters, models, clearFilters, hasActiveFilters])

  return (
    <SimpleCombobox
      options={sortedOptions}
      value={value}
      onValueChange={onValueChange}
      onToggleFavorite={handleToggleFavorite}
      placeholder={placeholder}
      searchPlaceholder="Search models..."
      emptyMessage="No models found."
      disabled={disabled}
      className={className}
      showFilters={showFilters}
      onToggleFilters={onToggleFilters}
      hasActiveFilters={hasActiveFilters}
      filterContent={filterContent}
      recentModelIds={recentModelIds}
      compact={compact}
      hideChevron={hideChevron}
      variant={variant}
    />
  )
})

function formatModelDescription(model: Model): string {
  const parts: string[] = []

  // Format price using centralized utility
  const promptFormatted = model.cost_per_1m_prompt != null
    ? pricingUtils.formatCost(model.cost_per_1m_prompt, model.cost_per_1m_prompt < 10 ? 2 : 0)
    : "$N/A"
  const completionFormatted = model.cost_per_1m_completion != null
    ? pricingUtils.formatCost(model.cost_per_1m_completion, model.cost_per_1m_completion < 10 ? 2 : 0)
    : "$N/A"

  parts.push(`${promptFormatted}/${completionFormatted} ${pricingUtils.getUnitLabelLong()}`)

  // Format max tokens
  if (model.max_tokens) {
    const formattedTokens = model.max_tokens >= 1000
      ? `${(model.max_tokens / 1000).toFixed(0)}K`
      : model.max_tokens.toString()
    parts.push(`${formattedTokens} tokens`)
  }

  // Add capabilities
  const capabilities: string[] = []
  if (model.supports_functions) capabilities.push("Tools")
  if (capabilities.length > 0) {
    parts.push(capabilities.join(", "))
  }

  return parts.join(" • ")
}