import { useState, useMemo } from 'react'
import type { ModelCatalogEntry } from '@/types/models'

export interface ModelFilters {
  search?: string
  provider?: string
  supportsFunctions?: boolean
  supportsStructuredOutputs?: boolean
  supportsReasoning?: boolean
  supportsPromptCaching?: boolean
  supportsStreamCancellation?: boolean
  input_modalities?: string[]  // For vision, audio, etc.
  maxPrice?: number
  minContext?: number
}

export function useModelFilters(models: ModelCatalogEntry[]) {
  const [showFilters, setShowFilters] = useState(false)
  const [filters, setFilters] = useState<ModelFilters>({
    search: '',
    provider: '',
    supportsFunctions: undefined,
    supportsStructuredOutputs: undefined,
    supportsReasoning: undefined,
    supportsPromptCaching: undefined,
    supportsStreamCancellation: undefined,
    input_modalities: undefined,
    maxPrice: undefined,
    minContext: undefined
  })

  // Extract unique providers
  const providers = useMemo(() => {
    const uniqueProviders = new Set(models.map((m) => m.provider))
    return Array.from(uniqueProviders).sort()
  }, [models])

  // Filter models based on filters
  const filteredModels = useMemo(() => {
    return models.filter(model => {
      // Search filter (optional, used in some contexts)
      if (filters.search) {
        const searchLower = filters.search.toLowerCase()
        if (!model.name.toLowerCase().includes(searchLower) &&
            !model.provider.toLowerCase().includes(searchLower) &&
            !model.model_id.toLowerCase().includes(searchLower)) {
          return false
        }
      }

      // Provider filter
      if (filters.provider && model.provider !== filters.provider) {
        return false
      }

      // Functions support filter
      if (filters.supportsFunctions !== undefined &&
          model.supports_functions !== filters.supportsFunctions) {
        return false
      }

      // Structured outputs support filter
      if (filters.supportsStructuredOutputs !== undefined &&
          model.supports_structured_outputs !== filters.supportsStructuredOutputs) {
        return false
      }

      // Reasoning support filter
      if (filters.supportsReasoning !== undefined &&
          model.supports_reasoning !== filters.supportsReasoning) {
        return false
      }

      // Prompt caching support filter
      if (filters.supportsPromptCaching !== undefined &&
          model.supports_prompt_caching !== filters.supportsPromptCaching) {
        return false
      }

      // Stream cancellation support filter
      if (filters.supportsStreamCancellation !== undefined &&
          model.supports_stream_cancellation !== filters.supportsStreamCancellation) {
        return false
      }

      // Input modalities filter (vision, audio, etc.)
      // Check that model supports ALL selected modalities
      if (filters.input_modalities && filters.input_modalities.length > 0) {
        for (const modality of filters.input_modalities) {
          if (!model.input_modalities?.includes(modality)) {
            return false
          }
        }
      }

      // Price filter (checking prompt price)
      if (filters.maxPrice !== undefined && model.cost_per_1m_prompt !== null) {
        if (model.cost_per_1m_prompt > filters.maxPrice) {
          return false
        }
      }

      // Min context filter
      if (filters.minContext !== undefined && model.max_tokens < filters.minContext) {
        return false
      }

      return true
    })
  }, [models, filters])

  // Check if any filters are active
  const hasActiveFilters = () => {
    return !!(
      filters.search ||
      filters.provider ||
      filters.supportsFunctions !== undefined ||
      filters.supportsStructuredOutputs !== undefined ||
      filters.supportsReasoning !== undefined ||
      filters.supportsPromptCaching !== undefined ||
      filters.supportsStreamCancellation !== undefined ||
      (filters.input_modalities && filters.input_modalities.length > 0) ||
      filters.maxPrice !== undefined ||
      filters.minContext !== undefined
    )
  }

  // Clear all filters
  const clearFilters = () => {
    setFilters({
      search: '',
      provider: '',
      supportsFunctions: undefined,
      supportsStructuredOutputs: undefined,
      supportsReasoning: undefined,
      supportsPromptCaching: undefined,
      supportsStreamCancellation: undefined,
      input_modalities: undefined,
      maxPrice: undefined,
      minContext: undefined
    })
  }

  return {
    // State
    showFilters,
    setShowFilters,
    filters,
    setFilters,

    // Computed
    providers,
    filteredModels,

    // Functions
    hasActiveFilters,
    clearFilters
  }
}
