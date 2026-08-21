import { Badge } from '@/components/ui/badge'
import { Separator } from '@/components/ui/separator'
import {
  Check,
  X,
  Image,
  FileText,
  MessageSquare,
  Mic,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import type { Model } from './types'
import { pricingUtils } from '@/lib/pricing-utils'
import { removeProviderPrefix } from '@/lib/model-utils'
import { ModelCapabilitiesBadges } from './ModelCapabilitiesBadges'
import { ModelIcon } from './ModelIcon'

interface ModelDetailsPopoverProps {
  model: Model
}

export function ModelDetailsPopover({ model }: ModelDetailsPopoverProps) {
  return (
    <div className="w-[350px] p-0">
      {/* Header */}
      <div className="bg-gradient-to-r from-accent-brand/10 to-accent-brand/5 p-4 rounded-t-lg border-b border-border">
        <div className="flex items-start gap-3">
          <div className="p-2 rounded-lg">
            <ModelIcon
              modelName={model.name}
              modelId={model.model_id}
              provider={model.provider}
              modelIconSlug={model.model_icon_slug}
              modelIconUrl={model.model_icon_url}
              providerIconSlug={model.provider_icon_slug}
              providerIconUrl={model.provider_icon_url}
              size={20}
              showTooltip={false}
            />
          </div>
          <div className="flex-1 min-w-0">
            <h3 className="font-semibold text-sm mb-1 leading-tight">{removeProviderPrefix(model.name, model.provider)}</h3>
            <div className="flex flex-wrap items-center gap-1.5">
              <Badge variant="outline" className="text-xs px-1.5 py-0">
                {model.provider}
              </Badge>
              {model.is_available !== undefined && (
                <Badge
                  variant="secondary"
                  className={cn(
                    'text-xs px-1.5 py-0',
                    model.is_available
                      ? 'bg-green-500/20 text-green-700 dark:text-green-400'
                      : 'bg-gray-500/20 text-gray-700 dark:text-gray-400'
                  )}
                >
                  {model.is_available ? (
                    <Check className="h-2.5 w-2.5" />
                  ) : (
                    <X className="h-2.5 w-2.5" />
                  )}
                </Badge>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Content */}
      <div className="p-4 space-y-3">
        {/* Pricing */}
        <div>
          <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">
            Pricing
          </h4>
          <div className="grid grid-cols-2 gap-2">
            <div className="p-2.5 rounded-md border border-border bg-secondary/30">
              <div className="mb-1">
                <span className="text-xs text-muted-foreground">Prompt</span>
              </div>
              <div className="text-sm font-bold">{pricingUtils.formatCost(model.cost_per_1m_prompt)}</div>
              <div className="text-xs text-muted-foreground">per {pricingUtils.getUnitLabel()}</div>
            </div>

            <div className="p-2.5 rounded-md border border-border bg-secondary/30">
              <div className="mb-1">
                <span className="text-xs text-muted-foreground">Completion</span>
              </div>
              <div className="text-sm font-bold">{pricingUtils.formatCost(model.cost_per_1m_completion)}</div>
              <div className="text-xs text-muted-foreground">per {pricingUtils.getUnitLabel()}</div>
            </div>
          </div>
        </div>

        <Separator />

        {/* Capabilities */}
        <div>
          <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">
            Capabilities
          </h4>
          <ModelCapabilitiesBadges model={model} displayMode="list" />
          {model.max_tokens && (
            <div className="flex items-center justify-between text-xs pt-2 mt-2 border-t border-border/50">
              <span className="text-muted-foreground">Max Context</span>
              <span className="font-medium">{model.max_tokens.toLocaleString()} tokens</span>
            </div>
          )}
        </div>

        <Separator />

        {/* Input Modalities */}
        <div>
          <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">
            Input Modalities
          </h4>
          <div className="flex flex-wrap gap-2">
            {model.input_modalities && model.input_modalities.length > 0 ? (
              model.input_modalities.map((modality) => {
                const getModalityIcon = () => {
                  switch (modality) {
                    case 'image':
                      return <Image className="h-3.5 w-3.5" />
                    case 'file':
                      return <FileText className="h-3.5 w-3.5" />
                    case 'audio':
                      return <Mic className="h-3.5 w-3.5" />
                    case 'text':
                    default:
                      return <MessageSquare className="h-3.5 w-3.5" />
                  }
                }

                const getModalityLabel = () => {
                  switch (modality) {
                    case 'image':
                      return 'Images'
                    case 'file':
                      return 'Documents'
                    case 'audio':
                      return 'Audio'
                    case 'text':
                    default:
                      return 'Text'
                  }
                }

                return (
                  <Badge
                    key={modality}
                    variant="secondary"
                    className="text-xs px-2 py-1 flex items-center gap-1.5 bg-accent-brand/10 text-accent-brand border-accent-brand/30"
                  >
                    {getModalityIcon()}
                    {getModalityLabel()}
                  </Badge>
                )
              })
            ) : (
              <Badge variant="secondary" className="text-xs px-2 py-1 flex items-center gap-1.5">
                <MessageSquare className="h-3.5 w-3.5" />
                Text
              </Badge>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
