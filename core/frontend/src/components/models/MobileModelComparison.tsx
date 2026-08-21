import { useState, useMemo } from 'react'
import {
  X,
  Check,
  DollarSign,
  Zap,
  Package,
  ChevronDown,
  ChevronUp,
  Code,
  Brain,
  Database,
  Image,
  Ban,
  Layout,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent } from '@/components/ui/card'
import { ModelIcon } from './ModelIcon'
import { ProviderIcon } from './ProviderIcon'
import useModelStore from '@/store/modelStore'
import type { ModelCatalogEntry } from '@/types/models'
import { pricingUtils } from '@/lib/pricing-utils'
import { removeProviderPrefix } from '@/lib/model-utils'

interface MobileModelComparisonProps {
  className?: string
}

type MetricKey = 'cost' | 'context' | 'capabilities' | 'speed'

interface ModelScore {
  model: ModelCatalogEntry
  costScore: number
  contextScore: number
  capabilityScore: number
  overallScore: number
}

type SortPreset = 'balanced' | 'budget' | 'context' | 'features'

const PRESETS: { id: SortPreset; label: string }[] = [
  { id: 'balanced', label: 'Balanced' },
  { id: 'budget', label: 'Budget' },
  { id: 'context', label: 'Context' },
  { id: 'features', label: 'Features' },
]

export function MobileModelComparison({ className }: MobileModelComparisonProps) {
  const { comparisonModels, removeFromComparison } = useModelStore()
  const [expandedModelId, setExpandedModelId] = useState<string | null>(null)
  const [activePreset, setActivePreset] = useState<SortPreset>('balanced')

  // Calculate scores for each model based on active preset
  const modelScores = useMemo((): ModelScore[] => {
    if (comparisonModels.length === 0) return []

    const minCost = Math.min(...comparisonModels.map(m => m.cost_per_1m_prompt + m.cost_per_1m_completion))
    const maxCost = Math.max(...comparisonModels.map(m => m.cost_per_1m_prompt + m.cost_per_1m_completion))
    const maxContext = Math.max(...comparisonModels.map(m => m.max_tokens))

    // Preset weights: [cost, context, capability]
    const weights: Record<SortPreset, [number, number, number]> = {
      balanced: [0.33, 0.33, 0.34],
      budget: [0.7, 0.1, 0.2],
      context: [0.1, 0.7, 0.2],
      features: [0.1, 0.2, 0.7],
    }
    const [costW, contextW, capW] = weights[activePreset]

    return comparisonModels.map(model => {
      const totalCost = model.cost_per_1m_prompt + model.cost_per_1m_completion
      // Cost score: lower is better (100 = cheapest, 0 = most expensive)
      const costScore = maxCost === minCost ? 100 : ((maxCost - totalCost) / (maxCost - minCost)) * 100

      // Context score: higher is better
      const contextScore = maxContext > 0 ? (model.max_tokens / maxContext) * 100 : 0

      // Capability score: count features
      let capabilityScore = 0
      if (model.supports_functions) capabilityScore += 20
      if (model.supports_structured_outputs) capabilityScore += 20
      if (model.supports_reasoning) capabilityScore += 20
      if (model.supports_prompt_caching) capabilityScore += 15
      if (model.supports_stream_cancellation) capabilityScore += 10

      const overallScore = (costScore * costW) + (contextScore * contextW) + (capabilityScore * capW)

      return {
        model,
        costScore,
        contextScore,
        capabilityScore,
        overallScore,
      }
    }).sort((a, b) => b.overallScore - a.overallScore)
  }, [comparisonModels, activePreset])

  // Find best in each category
  const bestInCategory = useMemo(() => {
    if (modelScores.length === 0) return { cost: null, context: null, capabilities: null }

    return {
      cost: modelScores.reduce((best, curr) => curr.costScore > best.costScore ? curr : best).model.model_id,
      context: modelScores.reduce((best, curr) => curr.contextScore > best.contextScore ? curr : best).model.model_id,
      capabilities: modelScores.reduce((best, curr) => curr.capabilityScore > best.capabilityScore ? curr : best).model.model_id,
    }
  }, [modelScores])

  const toggleExpand = (modelId: string) => {
    setExpandedModelId(prev => prev === modelId ? null : modelId)
  }

  if (comparisonModels.length === 0) {
    return (
      <div className={cn('flex flex-col items-center justify-center py-12 text-center px-4', className)}>
        <Package className="h-16 w-16 text-muted-foreground/30 mb-4" />
        <h3 className="font-semibold text-lg mb-2">No models to compare</h3>
        <p className="text-sm text-muted-foreground max-w-[280px]">
          Add models from the Browse tab to compare their features and costs side by side.
        </p>
      </div>
    )
  }

  return (
    <div className={cn('space-y-4', className)}>
      {/* Quick Summary Bar */}
      <div className="bg-muted/50 rounded-lg p-3">
        <div className="flex items-center justify-between mb-2">
          <span className="text-sm font-medium">Comparing {comparisonModels.length} models</span>
          <Button
            size="sm"
            variant="ghost"
            onClick={() => {
              comparisonModels.forEach(m => removeFromComparison(m.id))
            }}
            className="text-xs h-6 px-2 text-muted-foreground hover:text-foreground"
          >
            Clear all
          </Button>
        </div>
        {/* Preset buttons */}
        <div className="flex gap-1.5">
          {PRESETS.map((preset) => (
            <Button
              key={preset.id}
              size="sm"
              variant={activePreset === preset.id ? 'default' : 'outline'}
              className={cn(
                'h-7 text-xs flex-1',
                activePreset === preset.id && 'bg-accent-brand hover:bg-accent-brand/90'
              )}
              onClick={() => setActivePreset(preset.id)}
            >
              {preset.label}
            </Button>
          ))}
        </div>
      </div>

      {/* Model Cards */}
      <div className="space-y-3">
        {modelScores.map(({ model, costScore, contextScore, capabilityScore, overallScore }, index) => {
          const isExpanded = expandedModelId === model.model_id
          const isBest = index === 0
          const totalCost = model.cost_per_1m_prompt + model.cost_per_1m_completion

          return (
            <Card
              key={model.model_id}
              className={cn(
                'overflow-hidden transition-all relative',
                isBest && 'ring-2 ring-accent-brand border-accent-brand/50'
              )}
            >
              {/* Best Match corner badge */}
              {isBest && (
                <div className="absolute top-0 right-0 bg-accent-brand text-white text-[10px] font-medium px-2 py-0.5 rounded-bl-lg">
                  Best Match
                </div>
              )}
              <CardContent className="p-0">
                {/* Header - Always visible */}
                <div
                  className="p-4 cursor-pointer"
                  onClick={() => toggleExpand(model.model_id)}
                >
                  <div className="flex items-start gap-3">
                    {/* Model Icon */}
                    <ModelIcon
                      modelName={model.name}
                      modelId={model.model_id}
                      provider={model.provider}
                      modelIconSlug={model.model_icon_slug}
                      modelIconUrl={model.model_icon_url}
                      providerIconSlug={model.provider_icon_slug}
                      providerIconUrl={model.provider_icon_url}
                      size={40}
                      showTooltip={false}
                    />

                    {/* Model Info */}
                    <div className="flex-1 min-w-0">
                      <h3 className="font-semibold text-sm truncate">
                        {removeProviderPrefix(model.name, model.provider)}
                      </h3>
                      <div className="flex items-center gap-1.5 mt-0.5">
                        <ProviderIcon
                          provider={model.provider}
                          providerIconSlug={model.provider_icon_slug}
                          providerIconUrl={model.provider_icon_url}
                          size={12}
                          showTooltip={false}
                        />
                        <span className="text-xs text-muted-foreground">{model.provider}</span>
                      </div>
                    </div>

                    {/* Actions */}
                    <div className="flex items-center gap-1">
                      <Button
                        size="icon"
                        variant="ghost"
                        className="h-7 w-7"
                        onClick={(e) => {
                          e.stopPropagation()
                          removeFromComparison(model.model_id)
                        }}
                      >
                        <X className="h-4 w-4" />
                      </Button>
                      {isExpanded ? (
                        <ChevronUp className="h-4 w-4 text-muted-foreground" />
                      ) : (
                        <ChevronDown className="h-4 w-4 text-muted-foreground" />
                      )}
                    </div>
                  </div>

                  {/* Quick Stats - Always visible */}
                  <div className="grid grid-cols-3 gap-2 mt-3">
                    <div className={cn(
                      'text-center p-2 rounded-lg bg-muted/50',
                      bestInCategory.cost === model.model_id && 'bg-green-500/10 ring-1 ring-green-500/30'
                    )}>
                      <div className="text-xs text-muted-foreground mb-0.5">Cost</div>
                      <div className="text-sm font-semibold">
                        {pricingUtils.formatCostWithUnit(totalCost / 2)}
                      </div>
                      {bestInCategory.cost === model.model_id && (
                        <Badge variant="outline" className="text-[9px] px-1 py-0 h-3.5 mt-1 text-green-600 border-green-500/30">
                          Cheapest
                        </Badge>
                      )}
                    </div>
                    <div className={cn(
                      'text-center p-2 rounded-lg bg-muted/50',
                      bestInCategory.context === model.model_id && 'bg-blue-500/10 ring-1 ring-blue-500/30'
                    )}>
                      <div className="text-xs text-muted-foreground mb-0.5">Context</div>
                      <div className="text-sm font-semibold">
                        {(model.max_tokens / 1000).toFixed(0)}K
                      </div>
                      {bestInCategory.context === model.model_id && (
                        <Badge variant="outline" className="text-[9px] px-1 py-0 h-3.5 mt-1 text-blue-600 border-blue-500/30">
                          Largest
                        </Badge>
                      )}
                    </div>
                    <div className={cn(
                      'text-center p-2 rounded-lg bg-muted/50',
                      bestInCategory.capabilities === model.model_id && 'bg-purple-500/10 ring-1 ring-purple-500/30'
                    )}>
                      <div className="text-xs text-muted-foreground mb-0.5">Features</div>
                      <div className="text-sm font-semibold">
                        {Math.round(capabilityScore)}%
                      </div>
                      {bestInCategory.capabilities === model.model_id && (
                        <Badge variant="outline" className="text-[9px] px-1 py-0 h-3.5 mt-1 text-purple-600 border-purple-500/30">
                          Most
                        </Badge>
                      )}
                    </div>
                  </div>
                </div>

                {/* Expanded Details */}
                {isExpanded && (
                  <div className="px-4 pb-4 pt-0 border-t bg-muted/30">
                    {/* Pricing Details */}
                    <div className="py-3 border-b">
                      <div className="flex items-center gap-2 mb-2">
                        <DollarSign className="h-4 w-4 text-accent-brand" />
                        <span className="text-sm font-medium">Pricing</span>
                      </div>
                      <div className="grid grid-cols-2 gap-3 text-sm">
                        <div>
                          <span className="text-muted-foreground">Input: </span>
                          <span className="font-medium">{pricingUtils.formatCostWithUnit(model.cost_per_1m_prompt)}</span>
                        </div>
                        <div>
                          <span className="text-muted-foreground">Output: </span>
                          <span className="font-medium">{pricingUtils.formatCostWithUnit(model.cost_per_1m_completion)}</span>
                        </div>
                      </div>
                    </div>

                    {/* Technical Specs */}
                    <div className="py-3 border-b">
                      <div className="flex items-center gap-2 mb-2">
                        <Package className="h-4 w-4 text-accent-brand" />
                        <span className="text-sm font-medium">Technical Specs</span>
                      </div>
                      <div className="grid grid-cols-2 gap-3 text-sm">
                        <div>
                          <span className="text-muted-foreground">Max tokens: </span>
                          <span className="font-medium">{model.max_tokens.toLocaleString()}</span>
                        </div>
                        {model.max_completion_tokens && (
                          <div>
                            <span className="text-muted-foreground">Max output: </span>
                            <span className="font-medium">{model.max_completion_tokens.toLocaleString()}</span>
                          </div>
                        )}
                      </div>
                    </div>

                    {/* Capabilities */}
                    <div className="py-3">
                      <div className="flex items-center gap-2 mb-2">
                        <Zap className="h-4 w-4 text-accent-brand" />
                        <span className="text-sm font-medium">Capabilities</span>
                      </div>
                      <div className="flex flex-wrap gap-2">
                        <CapabilityBadge
                          label="Functions"
                          icon={Code}
                          supported={model.supports_functions}
                        />
                        <CapabilityBadge
                          label="Structured"
                          icon={Layout}
                          supported={model.supports_structured_outputs}
                        />
                        <CapabilityBadge
                          label="Reasoning"
                          icon={Brain}
                          supported={model.supports_reasoning}
                        />
                        <CapabilityBadge
                          label="Caching"
                          icon={Database}
                          supported={model.supports_prompt_caching}
                        />
                        <CapabilityBadge
                          label="Vision"
                          icon={Image}
                          supported={model.input_modalities?.includes('image')}
                        />
                        <CapabilityBadge
                          label="Cancel"
                          icon={Ban}
                          supported={model.supports_stream_cancellation}
                        />
                      </div>
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>
          )
        })}
      </div>
    </div>
  )
}

function CapabilityBadge({
  label,
  icon: Icon,
  supported,
}: {
  label: string
  icon: React.ComponentType<{ className?: string }>
  supported?: boolean
}) {
  return (
    <Badge
      variant="outline"
      className={cn(
        'text-xs gap-1',
        supported
          ? 'text-accent-brand border-accent-brand/30 bg-accent-brand/10'
          : 'text-muted-foreground/50 border-muted-foreground/20'
      )}
    >
      {supported ? (
        <Check className="h-3 w-3" />
      ) : (
        <X className="h-3 w-3" />
      )}
      <Icon className="h-3 w-3" />
      {label}
    </Badge>
  )
}
