import { useState, useEffect } from 'react'
import {
  Calculator,
  DollarSign,
  TrendingUp,
  MessageSquare,
  Code,
  FileText,
  Sparkles,
  Loader2Icon,
  ChevronDown,
  ChevronUp,
  ChevronRight,
  Check,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Slider } from '@/components/ui/slider'
import { Card, CardContent } from '@/components/ui/card'
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet'
import { ModelIcon } from './ModelIcon'
import useModelStore from '@/store/modelStore'
import { llmApi, type Model } from '@/api/llm'
import type { ModelCatalogEntry } from '@/types/models'
import { toModelCatalogEntry } from './modelCatalog'
import { pricingUtils } from '@/lib/pricing-utils'
import { removeProviderPrefix } from '@/lib/model-utils'

interface MobileCostCalculatorProps {
  selectedModel?: ModelCatalogEntry
  onModelSelect?: (model: ModelCatalogEntry) => void
  className?: string
}

const presets = [
  { name: 'Chat', icon: MessageSquare, prompt: 500, completion: 200, requests: 1000 },
  { name: 'Code', icon: Code, prompt: 1500, completion: 800, requests: 100 },
  { name: 'Docs', icon: FileText, prompt: 3000, completion: 500, requests: 50 },
  { name: 'Creative', icon: Sparkles, prompt: 1000, completion: 2000, requests: 10 },
]

export function MobileCostCalculator({
  selectedModel: propSelectedModel,
  onModelSelect,
  className,
}: MobileCostCalculatorProps) {
  const { comparisonModels } = useModelStore()
  const [allModels, setAllModels] = useState<ModelCatalogEntry[]>([])
  const [loadingModels, setLoadingModels] = useState(true)
  const [selectedModel, setSelectedModel] = useState<ModelCatalogEntry | null>(propSelectedModel || null)
  const [promptTokens, setPromptTokens] = useState(1000)
  const [completionTokens, setCompletionTokens] = useState(500)
  const [requestCount, setRequestCount] = useState(100)
  const [showAdvanced, setShowAdvanced] = useState(false)
  const [modelSheetOpen, setModelSheetOpen] = useState(false)

  // Fetch models
  useEffect(() => {
    const fetchAllModels = async () => {
      setLoadingModels(true)
      try {
        const firstPage = await llmApi.models({ available_only: true, page: 1 })
        const totalCount = firstPage.data.count
        const pageSize = firstPage.data.results.length
        const totalPages = Math.ceil(totalCount / pageSize)

        let rawModels: Model[] = []

        if (totalPages === 1) {
          rawModels = firstPage.data.results || []
        } else {
          const pagePromises = []
          for (let page = 1; page <= totalPages; page++) {
            pagePromises.push(llmApi.models({ available_only: true, page }))
          }
          const allResponses = await Promise.all(pagePromises)
          rawModels = allResponses.flatMap(res => res.data.results || [])
        }

        // Normalize to the catalog shape (also coerces string costs to numbers)
        setAllModels(rawModels.map(toModelCatalogEntry))
      } catch (error) {
        console.error('Failed to fetch models:', error)
        setAllModels([])
      } finally {
        setLoadingModels(false)
      }
    }

    fetchAllModels()
  }, [])

  useEffect(() => {
    if (propSelectedModel) {
      setSelectedModel(propSelectedModel)
    }
  }, [propSelectedModel])

  const handleModelSelect = (modelId: string) => {
    const model = allModels.find((m) => m.model_id === modelId)
    if (model) {
      setSelectedModel(model)
      onModelSelect?.(model)
    }
  }

  const applyPreset = (preset: typeof presets[0]) => {
    setPromptTokens(preset.prompt)
    setCompletionTokens(preset.completion)
    setRequestCount(preset.requests)
  }

  const calculateCost = (model: ModelCatalogEntry) => {
    const promptCost = pricingUtils.calculateCost(promptTokens, model.cost_per_1m_prompt)
    const completionCost = pricingUtils.calculateCost(completionTokens, model.cost_per_1m_completion)
    const totalCostPerRequest = promptCost + completionCost
    const totalCost = totalCostPerRequest * requestCount

    return {
      promptCost,
      completionCost,
      totalCostPerRequest,
      totalCost,
      monthlyCost: totalCost * 30,
    }
  }

  const selectedCost = selectedModel ? calculateCost(selectedModel) : null

  return (
    <div className={cn('space-y-4', className)}>
      {/* Big Cost Display */}
      {selectedModel && selectedCost && (
        <div className="bg-gradient-to-br from-accent-brand/20 to-accent-brand/5 rounded-xl p-5 text-center">
          <p className="text-xs text-muted-foreground uppercase tracking-wide mb-1">Total Cost</p>
          <p className="text-4xl font-bold text-accent-brand">
            {pricingUtils.formatCostDisplay(selectedCost.totalCost)}
          </p>
          <p className="text-sm text-muted-foreground mt-1">
            for {requestCount.toLocaleString()} requests
          </p>
          <div className="flex justify-center gap-4 mt-3 text-xs">
            <div>
              <span className="text-muted-foreground">Per request: </span>
              <span className="font-semibold">{pricingUtils.formatCostDisplay(selectedCost.totalCostPerRequest)}</span>
            </div>
            <div>
              <span className="text-muted-foreground">Monthly: </span>
              <span className="font-semibold">{pricingUtils.formatCostDisplay(selectedCost.monthlyCost)}</span>
            </div>
          </div>
        </div>
      )}

      {/* Quick Presets - Horizontal scroll on mobile */}
      <div>
        <p className="text-xs text-muted-foreground mb-2">Quick Presets</p>
        <div className="flex gap-2 overflow-x-auto pb-2 scrollbar-hide -mx-4 px-4">
          {presets.map((preset) => {
            const Icon = preset.icon
            return (
              <Button
                key={preset.name}
                variant="outline"
                size="sm"
                onClick={() => applyPreset(preset)}
                className="flex-shrink-0 gap-1.5 h-9"
              >
                <Icon className="h-3.5 w-3.5" />
                {preset.name}
              </Button>
            )
          })}
        </div>
      </div>

      {/* Model Selection */}
      <Card>
        <CardContent className="p-4 space-y-4">
          <div className="flex items-center gap-2 text-sm font-medium">
            <Calculator className="h-4 w-4 text-accent-brand" />
            Model
          </div>

          {loadingModels ? (
            <div className="flex items-center justify-center py-3 text-sm text-muted-foreground">
              <Loader2Icon className="h-4 w-4 mr-2 animate-spin" />
              Loading models...
            </div>
          ) : (
            <button
              onClick={() => setModelSheetOpen(true)}
              className="w-full flex items-center justify-between p-3 rounded-lg border bg-muted/30 hover:bg-muted/50 transition-colors"
            >
              <span className="text-sm text-muted-foreground">
                {selectedModel ? 'Change model...' : 'Select a model...'}
              </span>
              <ChevronRight className="h-4 w-4 text-muted-foreground" />
            </button>
          )}

          {selectedModel && (
            <div className="flex items-center gap-3 p-3 bg-muted/50 rounded-lg">
              <ModelIcon
                modelName={selectedModel.name}
                modelId={selectedModel.model_id}
                provider={selectedModel.provider}
                modelIconSlug={selectedModel.model_icon_slug}
                modelIconUrl={selectedModel.model_icon_url}
                providerIconSlug={selectedModel.provider_icon_slug}
                providerIconUrl={selectedModel.provider_icon_url}
                size={32}
                showTooltip={false}
              />
              <div className="flex-1 min-w-0">
                <p className="font-medium text-sm truncate">
                  {removeProviderPrefix(selectedModel.name, selectedModel.provider)}
                </p>
                <div className="flex gap-2 text-xs text-muted-foreground">
                  <span>In: {pricingUtils.formatCostWithUnit(selectedModel.cost_per_1m_prompt)}</span>
                  <span>Out: {pricingUtils.formatCostWithUnit(selectedModel.cost_per_1m_completion)}</span>
                </div>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Token Configuration */}
      <Card>
        <CardContent className="p-4 space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2 text-sm font-medium">
              <DollarSign className="h-4 w-4 text-accent-brand" />
              Usage
            </div>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setShowAdvanced(!showAdvanced)}
              className="h-7 text-xs gap-1"
            >
              {showAdvanced ? 'Simple' : 'Advanced'}
              {showAdvanced ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
            </Button>
          </div>

          {/* Request Count - Always visible */}
          <div>
            <div className="flex justify-between items-center mb-2">
              <span className="text-sm">API Calls</span>
              <Input
                type="number"
                value={requestCount}
                onChange={(e) => setRequestCount(Math.max(1, parseInt(e.target.value) || 1))}
                className="w-24 h-8 text-right text-sm"
                min={1}
              />
            </div>
            <div className="flex gap-1.5">
              {[10, 100, 1000, 10000].map((count) => (
                <Button
                  key={count}
                  variant={requestCount === count ? 'secondary' : 'outline'}
                  size="sm"
                  onClick={() => setRequestCount(count)}
                  className="flex-1 h-7 text-xs"
                >
                  {count >= 1000 ? `${count / 1000}K` : count}
                </Button>
              ))}
            </div>
          </div>

          {/* Advanced Options */}
          {showAdvanced && (
            <div className="space-y-4 pt-2 border-t">
              {/* Input Tokens */}
              <div>
                <div className="flex justify-between items-center mb-2">
                  <span className="text-sm">Input Tokens</span>
                  <Input
                    type="number"
                    value={promptTokens}
                    onChange={(e) => setPromptTokens(Math.max(0, parseInt(e.target.value) || 0))}
                    className="w-24 h-8 text-right text-sm"
                    min={0}
                  />
                </div>
                <Slider
                  value={[promptTokens]}
                  onValueChange={([value]) => setPromptTokens(value)}
                  min={0}
                  max={10000}
                  step={100}
                  className="py-2"
                />
                <p className="text-xs text-muted-foreground text-right">
                  ≈ {(promptTokens * 4).toLocaleString()} chars
                </p>
              </div>

              {/* Output Tokens */}
              <div>
                <div className="flex justify-between items-center mb-2">
                  <span className="text-sm">Output Tokens</span>
                  <Input
                    type="number"
                    value={completionTokens}
                    onChange={(e) => setCompletionTokens(Math.max(0, parseInt(e.target.value) || 0))}
                    className="w-24 h-8 text-right text-sm"
                    min={0}
                  />
                </div>
                <Slider
                  value={[completionTokens]}
                  onValueChange={([value]) => setCompletionTokens(value)}
                  min={0}
                  max={10000}
                  step={100}
                  className="py-2"
                />
                <p className="text-xs text-muted-foreground text-right">
                  ≈ {(completionTokens * 4).toLocaleString()} chars
                </p>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Cost Breakdown */}
      {selectedModel && selectedCost && (
        <Card>
          <CardContent className="p-4">
            <div className="flex items-center gap-2 text-sm font-medium mb-3">
              <TrendingUp className="h-4 w-4 text-accent-brand" />
              Cost Breakdown
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="bg-muted/50 rounded-lg p-3 text-center">
                <p className="text-xs text-muted-foreground mb-1">Input</p>
                <p className="font-semibold">
                  {pricingUtils.formatCostDisplay(selectedCost.promptCost * requestCount)}
                </p>
              </div>
              <div className="bg-muted/50 rounded-lg p-3 text-center">
                <p className="text-xs text-muted-foreground mb-1">Output</p>
                <p className="font-semibold">
                  {pricingUtils.formatCostDisplay(selectedCost.completionCost * requestCount)}
                </p>
              </div>
            </div>

            {/* Projected Costs */}
            <div className="mt-3 pt-3 border-t">
              <p className="text-xs text-muted-foreground mb-2">Projected (if {requestCount.toLocaleString()}/day)</p>
              <div className="flex justify-between text-sm">
                <span className="text-muted-foreground">Weekly</span>
                <span className="font-medium">{pricingUtils.formatCostDisplay(selectedCost.totalCost * 7)}</span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-muted-foreground">Monthly</span>
                <span className="font-medium">{pricingUtils.formatCostDisplay(selectedCost.monthlyCost)}</span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-muted-foreground">Yearly</span>
                <span className="font-medium">{pricingUtils.formatCostDisplay(selectedCost.totalCost * 365)}</span>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Model Comparison */}
      {comparisonModels.length > 1 && (
        <Card>
          <CardContent className="p-4">
            <div className="flex items-center gap-2 text-sm font-medium mb-3">
              <TrendingUp className="h-4 w-4" />
              Compare Models
            </div>
            <div className="space-y-2">
              {comparisonModels.map((model) => {
                const cost = calculateCost(model)
                const isSelected = model.model_id === selectedModel?.model_id
                const savings = selectedCost
                  ? ((selectedCost.totalCost - cost.totalCost) / selectedCost.totalCost * 100)
                  : 0

                return (
                  <div
                    key={model.model_id}
                    className={cn(
                      'flex items-center justify-between p-3 rounded-lg bg-muted/50',
                      isSelected && 'ring-2 ring-accent-brand bg-accent-brand/10'
                    )}
                    onClick={() => handleModelSelect(model.model_id)}
                  >
                    <div className="flex items-center gap-2 min-w-0">
                      <ModelIcon
                        modelName={model.name}
                        modelId={model.model_id}
                        provider={model.provider}
                        modelIconSlug={model.model_icon_slug}
                        modelIconUrl={model.model_icon_url}
                        providerIconSlug={model.provider_icon_slug}
                        providerIconUrl={model.provider_icon_url}
                        size={24}
                        showTooltip={false}
                      />
                      <span className="text-sm font-medium truncate">
                        {removeProviderPrefix(model.name, model.provider)}
                      </span>
                    </div>
                    <div className="text-right flex-shrink-0">
                      <p className="font-semibold text-sm">
                        {pricingUtils.formatCostDisplay(cost.totalCost)}
                      </p>
                      {selectedCost && !isSelected && Math.abs(savings) > 0.1 && (
                        <Badge
                          variant="outline"
                          className={cn(
                            'text-[10px] px-1.5 py-0',
                            savings > 0 ? 'text-green-600 border-green-500/30' : 'text-red-600 border-red-500/30'
                          )}
                        >
                          {savings > 0 ? '↓' : '↑'} {Math.abs(savings).toFixed(0)}%
                        </Badge>
                      )}
                    </div>
                  </div>
                )
              })}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Model Selection Sheet */}
      <Sheet open={modelSheetOpen} onOpenChange={setModelSheetOpen}>
        <SheetContent side="bottom" className="h-[70vh] rounded-t-xl">
          <SheetHeader className="pt-2 pb-4">
            <SheetTitle>Select a model</SheetTitle>
          </SheetHeader>
          <div className="overflow-y-auto h-[calc(100%-4rem)] -mx-6 px-6">
            <div className="space-y-1">
              {allModels.map((model) => {
                const isSelected = model.model_id === selectedModel?.model_id
                return (
                  <button
                    key={model.model_id}
                    onClick={() => {
                      handleModelSelect(model.model_id)
                      setModelSheetOpen(false)
                    }}
                    className={cn(
                      "w-full flex items-center gap-3 p-3 rounded-lg text-left transition-colors",
                      isSelected
                        ? "bg-accent-brand/10 ring-1 ring-accent-brand/30"
                        : "hover:bg-muted"
                    )}
                  >
                    <ModelIcon
                      modelName={model.name}
                      modelId={model.model_id}
                      provider={model.provider}
                      modelIconSlug={model.model_icon_slug}
                      modelIconUrl={model.model_icon_url}
                      providerIconSlug={model.provider_icon_slug}
                      providerIconUrl={model.provider_icon_url}
                      size={28}
                      showTooltip={false}
                    />
                    <div className="flex-1 min-w-0">
                      <div className="font-medium truncate text-sm">
                        {removeProviderPrefix(model.name, model.provider)}
                      </div>
                      <div className="text-xs text-muted-foreground truncate">{model.provider}</div>
                    </div>
                    <div className="text-right flex-shrink-0">
                      <div className="text-xs text-muted-foreground">
                        {pricingUtils.formatCostWithUnit((model.cost_per_1m_prompt + model.cost_per_1m_completion) / 2)}
                      </div>
                    </div>
                    {isSelected && (
                      <Check className="h-4 w-4 text-accent-brand flex-shrink-0" />
                    )}
                  </button>
                )
              })}
            </div>
          </div>
        </SheetContent>
      </Sheet>
    </div>
  )
}
