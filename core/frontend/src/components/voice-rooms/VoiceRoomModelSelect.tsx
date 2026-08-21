/**
 * Simple model selector for Voice Rooms
 *
 * A lightweight dropdown for selecting from the limited set of
 * voice room compatible models. No search, filters, or favorites needed.
 */

import { useMemo } from 'react'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { ModelIcon } from '@/components/models/ModelIcon'
import type { Model } from '@/components/models/types'
import { cn } from '@/lib/utils'

interface VoiceRoomModelSelectProps {
  models: Model[]
  value: string
  onValueChange: (value: string) => void
  className?: string
}

export function VoiceRoomModelSelect({
  models,
  value,
  onValueChange,
  className,
}: VoiceRoomModelSelectProps) {
  // Group models by provider for better organization
  const groupedModels = useMemo(() => {
    const groups: Record<string, Model[]> = {}
    models.forEach(model => {
      const provider = model.provider || 'Other'
      if (!groups[provider]) {
        groups[provider] = []
      }
      groups[provider].push(model)
    })
    // Sort providers alphabetically
    return Object.entries(groups).sort(([a], [b]) => a.localeCompare(b))
  }, [models])

  const selectedModel = models.find(m => m.model_id === value)

  return (
    <Select value={value} onValueChange={onValueChange}>
      <SelectTrigger className={cn("h-8 text-sm", className)}>
        <SelectValue placeholder="Select model">
          {selectedModel ? (
            <div className="flex items-center gap-2 min-w-0">
              <ModelIcon
                modelName={selectedModel.name}
                modelId={selectedModel.model_id}
                provider={selectedModel.provider}
                modelIconSlug={selectedModel.model_icon_slug}
                modelIconUrl={selectedModel.model_icon_url}
                providerIconSlug={selectedModel.provider_icon_slug}
                providerIconUrl={selectedModel.provider_icon_url}
                size={14}
                showTooltip={false}
              />
              <span className="truncate">{selectedModel.name}</span>
            </div>
          ) : (
            <span className="text-muted-foreground">Select a model</span>
          )}
        </SelectValue>
      </SelectTrigger>
      <SelectContent>
        {groupedModels.map(([provider, providerModels]) => (
          <div key={provider}>
            {/* Provider header */}
            <div className="px-2 py-1.5 text-[10px] font-medium text-muted-foreground uppercase tracking-wider">
              {provider}
            </div>
            {/* Models for this provider */}
            {providerModels.map(model => (
              <SelectItem
                key={model.model_id}
                value={model.model_id}
                className="py-2"
              >
                <div className="flex items-center gap-2">
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
                  <span>{model.name}</span>
                </div>
              </SelectItem>
            ))}
          </div>
        ))}
      </SelectContent>
    </Select>
  )
}
