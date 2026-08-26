/**
 * Model details modal state for ChatPanel: resolves a model id to its full
 * catalog entry, checking every model list the store tracks first, then the
 * chat's own messages for metadata, and finally falling back to a minimal
 * entry built from the panel's current model.
 */
import { useCallback, useState } from 'react'
import useModelStore from '@/store/modelStore'
import { toModelCatalogEntry } from '../modelCatalog'
import type { Message, Model } from '../types'
import type { ModelCatalogEntry } from '@/types/models'

export function useChatPanelModelDetails(model: Model | null, messages: Message[]) {
  const modelStore = useModelStore()
  const [isModelDetailsOpen, setIsModelDetailsOpen] = useState(false)
  const [selectedModelDetails, setSelectedModelDetails] = useState<ModelCatalogEntry | null>(null)

  const resolveModelDetails = useCallback((modelId?: string): ModelCatalogEntry | null => {
    if (!modelId) return null

    // First, try to find in model store
    const from = [
      modelStore.currentModel ? [modelStore.currentModel] : [],
      modelStore.models,
      modelStore.allModels,
      modelStore.recentModels.map(m => m.details).filter(Boolean) as ModelCatalogEntry[],
      modelStore.recentChatModels.map(m => m.details).filter(Boolean) as ModelCatalogEntry[],
      modelStore.favorites.map(f => f.details).filter(Boolean) as ModelCatalogEntry[],
      modelStore.comparisonModels,
    ].flat()
    const found = from.find(m => m.model_id === modelId)
    if (found) return found

    // If not found, search in messages to get metadata
    const messageWithModel = messages.find(msg => msg.model_id === modelId)
    if (messageWithModel && messageWithModel.model && messageWithModel.provider) {
      // Construct minimal entry from message metadata
      return toModelCatalogEntry({
        id: modelId,
        model_id: modelId,
        name: messageWithModel.model,
        provider: messageWithModel.provider,
        provider_icon_slug: messageWithModel.provider_icon_slug,
        provider_icon_url: messageWithModel.provider_icon_url,
        model_icon_slug: messageWithModel.model_icon_slug,
        model_icon_url: messageWithModel.model_icon_url,
        cost_per_1m_prompt: 0,
        cost_per_1m_completion: 0,
        max_tokens: 0,
        supports_streaming: true,
        supports_functions: false,
        supports_structured_outputs: false,
        supports_reasoning: false,
        supports_prompt_caching: false,
        supports_stream_cancellation: false,
        input_modalities: [],
        tags: [],
        is_available: true,
      })
    }

    return null
  }, [modelStore, messages])

  const openModelDetails = useCallback((modelId?: string) => {
    const targetModelId = modelId || model?.model_id
    const details = resolveModelDetails(targetModelId)
    if (details) {
      setSelectedModelDetails(details)
      setIsModelDetailsOpen(true)
    } else if (targetModelId && model) {
      // Final fallback: use current model info if nothing else worked
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
  }, [model, resolveModelDetails])

  return { isModelDetailsOpen, setIsModelDetailsOpen, selectedModelDetails, resolveModelDetails, openModelDetails }
}
