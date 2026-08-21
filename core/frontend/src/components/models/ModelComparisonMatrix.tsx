import { useState, useEffect, useMemo } from 'react'
import {
  X,
  Check,
  DollarSign,
  Zap,
  Code,
  Package,
  Shield,
  Layout,
  Brain,
  Database,
  Ban,
  Image,
  ChevronDown,
  ChevronUp,
  Loader2,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent } from '@/components/ui/card'
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import useModelStore from '@/store/modelStore'
import type { ModelCatalogEntry } from '@/types/models'
import { pricingUtils } from '@/lib/pricing-utils'
import { removeProviderPrefix } from '@/lib/model-utils'
import { ModelIcon } from './ModelIcon'
import { ProviderIcon } from './ProviderIcon'
import { openRouterApi } from '@/api/endpoints'
import type { CatalogModelScore, PriorityLevel } from '@/api/types'

interface ModelComparisonMatrixProps {
  models?: ModelCatalogEntry[]
  onRemoveModel?: (modelId: string) => void
  className?: string
}

type SortPreset = 'balanced' | 'budget' | 'context' | 'features'

const QUICK_PRESETS: { id: SortPreset; label: string; description: string }[] = [
  { id: 'balanced', label: 'Balanced', description: 'Equal weight to cost, context, and features' },
  { id: 'budget', label: 'Budget', description: 'Prioritize low cost' },
  { id: 'context', label: 'Context', description: 'Prioritize large context windows' },
  { id: 'features', label: 'Features', description: 'Prioritize capabilities' },
]

// Map UI presets to API priorities
const PRESET_TO_PRIORITIES: Record<SortPreset, {
  cost: PriorityLevel
  context: PriorityLevel
  capabilities: PriorityLevel
  multimodality: PriorityLevel
  availability: PriorityLevel
}> = {
  balanced: {
    cost: 'important',
    context: 'important',
    capabilities: 'important',
    multimodality: 'nice',
    availability: 'nice',
  },
  budget: {
    cost: 'critical',
    context: 'nice',
    capabilities: 'nice',
    multimodality: 'off',
    availability: 'important',
  },
  context: {
    cost: 'nice',
    context: 'critical',
    capabilities: 'important',
    multimodality: 'off',
    availability: 'important',
  },
  features: {
    cost: 'nice',
    context: 'important',
    capabilities: 'critical',
    multimodality: 'nice',
    availability: 'important',
  },
}

export function ModelComparisonMatrix({
  models: propModels,
  onRemoveModel,
  className,
}: ModelComparisonMatrixProps) {
  const { comparisonModels, removeFromComparison } = useModelStore()
  const models = propModels || comparisonModels

  const [expandedModelIds, setExpandedModelIds] = useState<Set<string>>(new Set())
  const [activePreset, setActivePreset] = useState<SortPreset>('balanced')
  const [isLoading, setIsLoading] = useState(false)
  const [scores, setScores] = useState<CatalogModelScore[]>([])
  const [bestModelId, setBestModelId] = useState<string | null>(null)

  // Fetch comparison from backend when models or preset changes
  useEffect(() => {
    if (models.length === 0) {
      setScores([])
      setBestModelId(null)
      return
    }

    const fetchComparison = async () => {
      setIsLoading(true)
      try {
        const response = await openRouterApi.compareCatalog({
          model_ids: models.map(m => m.model_id),
          priorities: PRESET_TO_PRIORITIES[activePreset],
        })
        setScores(response.data.scores)
        setBestModelId(response.data.best_model_id)
      } catch (error) {
        console.error('Failed to compare models:', error)
        setScores([])
        setBestModelId(null)
      } finally {
        setIsLoading(false)
      }
    }

    fetchComparison()
  }, [models, activePreset])

  // Create a lookup for model data by model_id
  const modelLookup = useMemo(() => {
    const map = new Map<string, ModelCatalogEntry>()
    models.forEach(m => map.set(m.model_id, m))
    return map
  }, [models])

  // Find best in each category from scores
  const bestInCategory = useMemo(() => {
    if (scores.length === 0) return { cost: null, context: null, capabilities: null }

    let bestCost = scores[0]
    let bestContext = scores[0]
    let bestCaps = scores[0]

    for (const score of scores) {
      if (score.breakdown.cost > bestCost.breakdown.cost) bestCost = score
      if (score.breakdown.context > bestContext.breakdown.context) bestContext = score
      if (score.breakdown.capabilities > bestCaps.breakdown.capabilities) bestCaps = score
    }

    return {
      cost: bestCost.id,
      context: bestContext.id,
      capabilities: bestCaps.id,
    }
  }, [scores])

  const handleRemove = (modelId: string) => {
    if (onRemoveModel) {
      onRemoveModel(modelId)
    } else {
      removeFromComparison(modelId)
    }
  }

  const toggleExpand = (modelId: string) => {
    setExpandedModelIds(prev => {
      const next = new Set(prev)
      if (next.has(modelId)) {
        next.delete(modelId)
      } else {
        next.add(modelId)
      }
      return next
    })
  }

  if (models.length === 0) {
    return (
      <div className={cn(
        'flex flex-col items-center justify-center py-16 border-2 border-dashed rounded-lg',
        className
      )}>
        <Package className="h-16 w-16 text-muted-foreground/30 mb-4" />
        <h3 className="font-semibold text-lg mb-2">No models to compare</h3>
        <p className="text-sm text-muted-foreground text-center max-w-md">
          Add models from the Browse tab to compare their features, costs, and capabilities side by side.
        </p>
      </div>
    )
  }

  return (
    <div className={cn('space-y-4', className)}>
      {/* Header with presets and controls */}
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <div className="flex items-center gap-2">
          <span className="text-sm text-muted-foreground">Comparing {models.length} models</span>
          {isLoading && <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />}
          <Button
            variant="ghost"
            size="sm"
            onClick={() => models.forEach(m => handleRemove(m.id))}
            className="h-7 text-xs text-muted-foreground hover:text-foreground"
          >
            Clear all
          </Button>
        </div>

        {/* Quick Presets */}
        <TooltipProvider>
          <div className="flex gap-1 bg-muted/50 p-1 rounded-lg">
            {QUICK_PRESETS.map((preset) => (
              <Tooltip key={preset.id}>
                <TooltipTrigger asChild>
                  <Button
                    size="sm"
                    variant={activePreset === preset.id ? 'default' : 'ghost'}
                    className={cn(
                      'h-7 text-xs px-3',
                      activePreset === preset.id && 'bg-accent-brand hover:bg-accent-brand/90'
                    )}
                    onClick={() => setActivePreset(preset.id)}
                    disabled={isLoading}
                  >
                    {preset.label}
                  </Button>
                </TooltipTrigger>
                <TooltipContent>
                  <p className="text-xs">{preset.description}</p>
                </TooltipContent>
              </Tooltip>
            ))}
          </div>
        </TooltipProvider>
      </div>

      {/* Model Cards Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
        {scores.map((score, index) => {
          const model = modelLookup.get(score.id)
          if (!model) return null

          const isExpanded = expandedModelIds.has(model.model_id)
          const isBest = score.is_best
          const totalCost = model.cost_per_1m_prompt + model.cost_per_1m_completion

          return (
            <Card
              key={model.model_id}
              className={cn(
                'overflow-hidden transition-all relative',
                isBest && 'ring-2 ring-accent-brand border-accent-brand/50'
              )}
            >
              {/* Best Match badge */}
              {isBest && (
                <div className="absolute top-0 right-0 bg-accent-brand text-white text-[10px] font-medium px-2 py-0.5 rounded-bl-lg z-10">
                  Best Match
                </div>
              )}

              <CardContent className="p-0">
                {/* Header */}
                <div
                  className="p-4 cursor-pointer hover:bg-muted/30 transition-colors"
                  onClick={() => toggleExpand(model.model_id)}
                >
                  <div className="flex items-start gap-3">
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

                    <div className="flex-1 min-w-0">
                      <h3 className="font-semibold text-sm truncate pr-16">
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

                    <div className="flex items-center gap-1">
                      <Button
                        size="icon"
                        variant="ghost"
                        className="h-7 w-7"
                        onClick={(e) => {
                          e.stopPropagation()
                          handleRemove(model.id)
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

                  {/* Quick Stats */}
                  <div className="grid grid-cols-3 gap-2 mt-4">
                    <ScoreCell
                      label="Cost"
                      value={pricingUtils.formatCostWithUnit(totalCost / 2)}
                      score={score.breakdown.cost * 100 / 3}  // Normalize from weight to percentage
                      isBest={bestInCategory.cost === model.model_id}
                      bestLabel="Cheapest"
                      color="green"
                    />
                    <ScoreCell
                      label="Context"
                      value={score.context_str}
                      score={score.breakdown.context * 100 / 3}
                      isBest={bestInCategory.context === model.model_id}
                      bestLabel="Largest"
                      color="blue"
                    />
                    <ScoreCell
                      label="Features"
                      value={`${score.capabilities.length}`}
                      score={score.breakdown.capabilities * 100 / 3}
                      isBest={bestInCategory.capabilities === model.model_id}
                      bestLabel="Most"
                      color="purple"
                    />
                  </div>

                  {/* Overall Score Bar */}
                  <div className="mt-3">
                    <div className="flex items-center justify-between text-xs mb-1">
                      <span className="text-muted-foreground">Overall Score</span>
                      <span className="font-medium">{Math.round(score.score_pct)}%</span>
                    </div>
                    <div className="h-1.5 bg-muted rounded-full overflow-hidden">
                      <div
                        className="h-full bg-accent-brand rounded-full transition-all"
                        style={{ width: `${score.score_pct}%` }}
                      />
                    </div>
                  </div>
                </div>

                {/* Expanded Details */}
                {isExpanded && (
                  <div className="px-4 pb-4 pt-0 border-t bg-muted/20">
                    {/* Pricing */}
                    <DetailSection icon={DollarSign} title="Pricing">
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
                    </DetailSection>

                    {/* Technical Specs */}
                    <DetailSection icon={Package} title="Technical">
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
                    </DetailSection>

                    {/* Capabilities */}
                    <DetailSection icon={Zap} title="Capabilities" noBorder>
                      <div className="flex flex-wrap gap-1.5">
                        <CapabilityBadge label="Functions" icon={Code} supported={model.supports_functions} />
                        <CapabilityBadge label="Structured" icon={Layout} supported={model.supports_structured_outputs} />
                        <CapabilityBadge label="Reasoning" icon={Brain} supported={model.supports_reasoning} />
                        <CapabilityBadge label="Caching" icon={Database} supported={model.supports_prompt_caching} />
                        <CapabilityBadge label="Vision" icon={Image} supported={model.input_modalities?.includes('image')} />
                        <CapabilityBadge label="Cancel" icon={Ban} supported={model.supports_stream_cancellation} />
                      </div>
                    </DetailSection>

                    {/* Availability */}
                    <div className="flex items-center justify-between pt-3 mt-3 border-t">
                      <div className="flex items-center gap-2 text-sm">
                        <Shield className="h-4 w-4 text-muted-foreground" />
                        <span className="text-muted-foreground">Status</span>
                      </div>
                      <div className="flex gap-2">
                        {model.is_available ? (
                          <Badge variant="outline" className="text-xs text-accent-brand border-accent-brand/30">
                            Available
                          </Badge>
                        ) : (
                          <Badge variant="outline" className="text-xs text-destructive border-destructive/30">
                            Unavailable
                          </Badge>
                        )}
                        {model.is_moderated && (
                          <Badge variant="outline" className="text-xs">Moderated</Badge>
                        )}
                      </div>
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>
          )
        })}
      </div>

      {/* Summary Cards */}
      {scores.length > 0 && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          <SummaryCard
            icon={DollarSign}
            title="Most Cost-Effective"
            value={
              bestInCategory.cost
                ? removeProviderPrefix(
                    modelLookup.get(bestInCategory.cost)?.name || '',
                    modelLookup.get(bestInCategory.cost)?.provider || ''
                  )
                : 'N/A'
            }
            subtitle={
              bestInCategory.cost
                ? pricingUtils.formatCostWithUnit(
                    (modelLookup.get(bestInCategory.cost)?.cost_per_1m_prompt || 0) +
                    (modelLookup.get(bestInCategory.cost)?.cost_per_1m_completion || 0)
                  ) + ' avg'
                : ''
            }
          />
          <SummaryCard
            icon={Package}
            title="Largest Context"
            value={
              bestInCategory.context
                ? removeProviderPrefix(
                    modelLookup.get(bestInCategory.context)?.name || '',
                    modelLookup.get(bestInCategory.context)?.provider || ''
                  )
                : 'N/A'
            }
            subtitle={
              bestInCategory.context
                ? `${(modelLookup.get(bestInCategory.context)?.max_tokens || 0).toLocaleString()} tokens`
                : ''
            }
          />
          <SummaryCard
            icon={Zap}
            title="Most Capable"
            value={
              bestInCategory.capabilities
                ? removeProviderPrefix(
                    modelLookup.get(bestInCategory.capabilities)?.name || '',
                    modelLookup.get(bestInCategory.capabilities)?.provider || ''
                  )
                : 'N/A'
            }
            subtitle={
              bestInCategory.capabilities
                ? `${scores.find(s => s.id === bestInCategory.capabilities)?.capabilities.length || 0} features`
                : ''
            }
          />
          <SummaryCard
            icon={Shield}
            title="Availability"
            value={`${models.filter(m => m.is_available).length}/${models.length}`}
            subtitle="models available"
          />
        </div>
      )}
    </div>
  )
}

function ScoreCell({
  label,
  value,
  score,
  isBest,
  bestLabel,
  color,
}: {
  label: string
  value: string
  score: number
  isBest: boolean
  bestLabel: string
  color: 'green' | 'blue' | 'purple'
}) {
  const colorClasses = {
    green: 'bg-green-500/10 ring-green-500/30 text-green-600',
    blue: 'bg-blue-500/10 ring-blue-500/30 text-blue-600',
    purple: 'bg-purple-500/10 ring-purple-500/30 text-purple-600',
  }

  return (
    <div className={cn(
      'text-center p-2 rounded-lg bg-muted/50 h-[72px] flex flex-col justify-center',
      isBest && `${colorClasses[color].split(' ').slice(0, 2).join(' ')} ring-1`
    )}>
      <div className="text-xs text-muted-foreground mb-0.5">{label}</div>
      <div className="text-sm font-semibold">{value}</div>
      <div className="h-4 flex items-center justify-center">
        {isBest && (
          <Badge
            variant="outline"
            className={cn('text-[9px] px-1 py-0 h-3.5', colorClasses[color].split(' ')[2], `border-${color}-500/30`)}
          >
            {bestLabel}
          </Badge>
        )}
      </div>
    </div>
  )
}

function DetailSection({
  icon: Icon,
  title,
  children,
  noBorder = false,
}: {
  icon: React.ComponentType<{ className?: string }>
  title: string
  children: React.ReactNode
  noBorder?: boolean
}) {
  return (
    <div className={cn('py-3', !noBorder && 'border-b')}>
      <div className="flex items-center gap-2 mb-2">
        <Icon className="h-4 w-4 text-accent-brand" />
        <span className="text-sm font-medium">{title}</span>
      </div>
      {children}
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
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          <Badge
            variant="outline"
            className={cn(
              'text-xs gap-1 cursor-default',
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
        </TooltipTrigger>
        <TooltipContent>
          <p className="text-xs">{label}: {supported ? 'Supported' : 'Not supported'}</p>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  )
}

function SummaryCard({
  icon: Icon,
  title,
  value,
  subtitle,
}: {
  icon: React.ComponentType<{ className?: string }>
  title: string
  value: string
  subtitle: string
}) {
  return (
    <Card className="bg-muted/30">
      <CardContent className="p-3">
        <div className="flex items-center gap-2 text-xs text-muted-foreground mb-1">
          <Icon className="h-3.5 w-3.5 text-accent-brand" />
          {title}
        </div>
        <p className="font-semibold text-sm truncate">{value}</p>
        <p className="text-xs text-muted-foreground truncate">{subtitle}</p>
      </CardContent>
    </Card>
  )
}
