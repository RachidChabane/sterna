/**
 * ModelCapabilitiesBadges Component
 *
 * Centralized component for displaying model capabilities and modalities.
 * Supports two display modes:
 * - "badge": Displays capabilities as badges with tooltips (for catalog)
 * - "list": Displays capabilities as a list with icons and checkmarks (for popovers)
 */

import { Badge } from '@/components/ui/badge'
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import {
  Code,
  Braces,
  Brain,
  Database,
  Ban,
  Camera,
  Mic,
  Check,
  X,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import type { Model } from './types'

interface ModelCapabilitiesBadgesProps {
  model: Model
  displayMode?: 'badge' | 'list'
  className?: string
}

interface Capability {
  id: string
  label: string
  icon: typeof Code
  tooltip: string
  isSupported: (model: Model) => boolean
}

// Centralized capability definitions
const capabilities: Capability[] = [
  {
    id: 'functions',
    label: 'Tools',
    icon: Code,
    tooltip: 'Tool calling support - model can use external tools and APIs',
    isSupported: (model) => model.supports_functions ?? false,
  },
  {
    id: 'structured',
    label: 'Structured',
    icon: Braces,
    tooltip: 'JSON schema validation - reliable structured data output',
    isSupported: (model) => model.supports_structured_outputs ?? false,
  },
  {
    id: 'reasoning',
    label: 'Reasoning',
    icon: Brain,
    tooltip: 'Reasoning tokens - model can show its thinking process',
    isSupported: (model) => model.supports_reasoning ?? false,
  },
  {
    id: 'prompt-caching',
    label: 'Caching',
    icon: Database,
    tooltip: 'Prompt caching - faster and cheaper responses for repeated prompts',
    isSupported: (model) => model.supports_prompt_caching ?? false,
  },
  {
    id: 'stream-cancellation',
    label: 'Cancellation',
    icon: Ban,
    tooltip: 'Cancel streaming responses mid-generation',
    isSupported: (model) => model.supports_stream_cancellation ?? false,
  },
  {
    id: 'vision',
    label: 'Vision',
    icon: Camera,
    tooltip: 'Supports image inputs - multimodal model',
    isSupported: (model) => model.input_modalities?.includes('image') ?? false,
  },
  {
    id: 'audio',
    label: 'Audio',
    icon: Mic,
    tooltip: 'Supports audio inputs',
    isSupported: (model) => model.input_modalities?.includes('audio') ?? false,
  },
]

export function ModelCapabilitiesBadges({
  model,
  displayMode = 'badge',
  className,
}: ModelCapabilitiesBadgesProps) {
  if (displayMode === 'badge') {
    return (
      <TooltipProvider>
        <div className={cn('flex flex-wrap gap-2', className)}>
          {capabilities.map((capability) => {
            const Icon = capability.icon
            const isSupported = capability.isSupported(model)

            if (!isSupported) return null

            return (
              <Tooltip key={capability.id}>
                <TooltipTrigger asChild>
                  <Badge variant="outline" className="text-xs bg-background/50">
                    <Icon className="h-3 w-3 mr-1" />
                    {capability.label}
                  </Badge>
                </TooltipTrigger>
                <TooltipContent>
                  {capability.tooltip}
                </TooltipContent>
              </Tooltip>
            )
          })}
        </div>
      </TooltipProvider>
    )
  }

  // List mode for popovers
  return (
    <div className={cn('space-y-1.5', className)}>
      {capabilities.map((capability) => {
        const Icon = capability.icon
        const isSupported = capability.isSupported(model)

        return (
          <div
            key={capability.id}
            className="flex items-center justify-between text-xs"
          >
            <div className="flex items-center gap-1.5">
              <Icon
                className={cn(
                  'h-3.5 w-3.5',
                  isSupported ? 'text-accent-brand' : 'text-muted-foreground'
                )}
              />
              <span>{capability.label}</span>
            </div>
            {isSupported ? (
              <Check className="h-3.5 w-3.5 text-accent-brand" />
            ) : (
              <X className="h-3.5 w-3.5 text-muted-foreground" />
            )}
          </div>
        )
      })}
    </div>
  )
}
