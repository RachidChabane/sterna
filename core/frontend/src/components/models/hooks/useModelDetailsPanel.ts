/**
 * Model details modal state: resolves a model id to its full catalog entry
 * (checked across every model list the store tracks) and falls back to a
 * minimal entry built from the chat's current model when no catalog match
 * is found.
 */
import { useCallback, useState } from 'react'
import useModelStore from '@/store/modelStore'
import type { Model } from '../types'
import type { ModelCatalogEntry } from '@/types/models'

export function useModelDetailsPanel(model: Model | null) {
  const modelStore = useModelStore()
  const [isModelDetailsOpen, setIsModelDetailsOpen] = useState(false)
  const [selectedModelDetails, setSelectedModelDetails] = useState<ModelCatalogEntry | null>(null)

  const handleOpenModelDetails = useCallback((modelId?: string) => {
    const targetModelId = modelId || model?.model_id
    if (!targetModelId) return

    // Try to find model details from model store
    const from = [
      modelStore.currentModel ? [modelStore.currentModel] : [],
      modelStore.models,
      modelStore.allModels,
      modelStore.recentModels.map(m => m.details).filter(Boolean) as ModelCatalogEntry[],
      modelStore.recentChatModels.map(m => m.details).filter(Boolean) as ModelCatalogEntry[],
      modelStore.favorites.map(f => f.details).filter(Boolean) as ModelCatalogEntry[],
      modelStore.comparisonModels,
    ].flat()
    const found = from.find(m => m.model_id === targetModelId)

    if (found) {
      setSelectedModelDetails(found)
      setIsModelDetailsOpen(true)
    } else if (model) {
      // Fallback: create minimal details from current model
      const minimal: ModelCatalogEntry = {
        id: targetModelId,
        model_id: targetModelId,
        name: model.name || targetModelId,
        provider: model.provider || 'unknown',
        provider_icon_slug: model.provider_icon_slug,
        provider_icon_url: model.provider_icon_url,
        model_icon_slug: model.model_icon_slug,
        model_icon_url: model.model_icon_url,
        cost_per_1m_prompt: 0,
        cost_per_1m_completion: 0,
        max_tokens: model.max_tokens || 0,
        supports_streaming: true,
        supports_functions: Boolean(model.supports_functions),
        supports_structured_outputs: Boolean(model.supports_structured_outputs),
        supports_reasoning: Boolean(model.supports_reasoning),
        supports_prompt_caching: Boolean(model.supports_prompt_caching),
        supports_stream_cancellation: true,
        modality: null,
        input_modalities: model.input_modalities || [],
        output_modalities: model.output_modalities || ['text'],
        tokenizer: null,
        max_completion_tokens: null,
        is_moderated: false,
        default_parameters: {},
        description: undefined,
        tags: [],
        is_available: true,
        fetched_at: new Date().toISOString(),
      }
      setSelectedModelDetails(minimal)
      setIsModelDetailsOpen(true)
    }
  }, [model, modelStore])

  return { isModelDetailsOpen, setIsModelDetailsOpen, selectedModelDetails, handleOpenModelDetails }
}
