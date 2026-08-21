import React from 'react'
import { Cpu, Star, Check } from 'lucide-react'
import type { CommandProvider, ModelCommandItem } from '../types'
import type { ModelStore } from '@/store/modelStore'
import { matchQuery, scoreMatch } from '../utils/search'
import { removeProviderPrefix } from '@/lib/model-utils'

/**
 * Models Provider Factory
 *
 * Provides search for AI models with actions (favorite, select)
 * Factory pattern to inject store dependencies
 */
export function createModelsProvider(getStore: () => ModelStore): CommandProvider {
  return {
    id: 'models',
    name: 'Models',
    icon: Cpu,
    priority: 2, // Show after pages and conversations

    async getItems(query: string): Promise<ModelCommandItem[]> {
      const store = getStore()
      const {
        allModels,
        allModelsLoaded,
        allModelsLoading,
        fetchAllModels,
        favorites,
        selectedModels,
        currentModel,
        addFavorite,
        removeFavorite,
        toggleModelSelection,
        setCurrentModel,
      } = store

      // Load all models if not already loaded
      if (!allModelsLoaded && !allModelsLoading) {
        await fetchAllModels()
      }

      // Wait for models to load
      if (allModelsLoading || allModels.length === 0) {
        return []
      }

      // Filter models by query
      const filtered = allModels.filter((model) => {
        const nameMatch = matchQuery(model.name, query)
        const providerMatch = matchQuery(model.provider, query)
        const idMatch = matchQuery(model.model_id, query)
        return nameMatch || providerMatch || idMatch
      })

      // Score and sort
      const scored = filtered.map((model) => ({
        model,
        score: Math.max(
          scoreMatch(model.name, query),
          scoreMatch(model.provider, query),
          scoreMatch(model.model_id, query)
        ),
      }))

      scored.sort((a, b) => b.score - a.score)

      // Limit to 20 models for performance
      const limited = scored.slice(0, 20)

      // Convert to ModelCommandItems
      return limited.map(({ model }) => {
        const isFavorite = favorites.some((f) => f.model_id === model.model_id)
        const isSelected = selectedModels.has(model.model_id)
        const isCurrent = currentModel?.model_id === model.model_id

        return {
          id: model.model_id,
          type: 'model' as const,
          title: removeProviderPrefix(model.name, model.provider),
          subtitle: `${model.provider}${model.max_tokens ? ` • ${(model.max_tokens / 1000).toFixed(0)}k ctx` : ''}`,
          // Icon will be rendered as ModelIcon component
          icon: Cpu, // Placeholder, will be replaced with ModelIcon in component
          modelId: model.model_id,
          provider: model.provider,
          isFavorite,
          isSelected,
          isCurrent,
          badge: isCurrent ? 'Current' : undefined,
          actions: [
            {
              label: isFavorite ? 'Remove from favorites' : 'Add to favorites',
              icon: <Star className="h-3.5 w-3.5" />,
              onClick: (e: React.MouseEvent) => {
                e.stopPropagation()
                if (isFavorite) {
                  removeFavorite(model.model_id)
                } else {
                  addFavorite(model.model_id, model)
                }
              },
            },
            {
              label: isSelected ? 'Deselect' : 'Select',
              icon: <Check className="h-3.5 w-3.5" />,
              onClick: (e: React.MouseEvent) => {
                e.stopPropagation()
                toggleModelSelection(model.model_id)
              },
            },
          ],
          onSelect: () => {
            setCurrentModel(model)
          },
          // Store full model data for rendering ModelIcon
          _modelData: model,
        } as any // Type assertion to add _modelData
      })
    },

    isEnabled(): boolean {
      // Always enabled
      return true
    },
  }
}
