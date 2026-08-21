import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Separator } from '@/components/ui/separator'
import {
  DollarSign,
  Code,
  Check,
  X,
  Info,
  Package,
  Braces,
  Brain,
  Database,
  Ban,
  Camera,
  Mic,
  FileText,
  Clock,
  Zap,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import type { ModelCatalogEntry } from '@/types/models'
import { ModelIcon } from './ModelIcon'
import { ProviderIcon } from './ProviderIcon'
import { pricingUtils } from '@/lib/pricing-utils'
import { removeProviderPrefix } from '@/lib/model-utils'
import { Markdown } from '@/components/ui/markdown'

interface ModelDetailsModalProps {
  isOpen: boolean
  onClose: () => void
  model: ModelCatalogEntry | null
  onSelectModel?: (model: ModelCatalogEntry) => void
  selectedModelId?: string
}

export function ModelDetailsModal({
  isOpen,
  onClose,
  model,
  onSelectModel,
  selectedModelId,
}: ModelDetailsModalProps) {
  if (!model) return null

  const isSelected = selectedModelId === model.model_id

  const handleSelect = () => {
    if (onSelectModel) {
      onSelectModel(model)
      onClose()
    }
  }

  return (
    <Dialog open={isOpen} onOpenChange={onClose}>
      <DialogContent className="max-w-3xl max-h-[85vh] md:max-h-[85vh] h-[100dvh] md:h-auto p-0 gap-0 flex flex-col">
        {/* Header - Mobile: centered, compact. Desktop: side-by-side */}
        <div className="flex-shrink-0 bg-background border-b border-border p-4 md:p-6 md:pb-4 rounded-t-lg">
          <DialogHeader>
            {/* Mobile Header - Centered */}
            <div className="md:hidden flex flex-col items-center text-center">
              <ModelIcon
                modelName={model.name}
                modelId={model.model_id}
                provider={model.provider}
                modelIconSlug={model.model_icon_slug}
                modelIconUrl={model.model_icon_url}
                providerIconSlug={model.provider_icon_slug}
                providerIconUrl={model.provider_icon_url}
                size={48}
                showTooltip={false}
              />
              <DialogTitle className="text-xl mt-3 mb-1">{removeProviderPrefix(model.name, model.provider)}</DialogTitle>
              <DialogDescription className="text-xs mb-2">
                <code className="bg-secondary px-2 py-0.5 rounded text-[11px]">
                  {model.model_id}
                </code>
              </DialogDescription>
              <Badge
                variant={model.is_available ? 'default' : 'secondary'}
                className={cn(
                  'text-xs',
                  model.is_available
                    ? 'bg-green-500/20 text-green-700 dark:text-green-400'
                    : 'bg-gray-500/20 text-gray-700 dark:text-gray-400'
                )}
              >
                {model.is_available ? (
                  <>
                    <Check className="h-3 w-3 mr-1" />
                    Available
                  </>
                ) : (
                  <>
                    <X className="h-3 w-3 mr-1" />
                    Unavailable
                  </>
                )}
              </Badge>
            </div>

            {/* Desktop Header - Side by side */}
            <div className="hidden md:flex items-start gap-4">
              <div className="p-3 rounded-xl flex items-center justify-center">
                <ModelIcon
                  modelName={model.name}
                  modelId={model.model_id}
                  provider={model.provider}
                  modelIconSlug={model.model_icon_slug}
                  modelIconUrl={model.model_icon_url}
                  providerIconSlug={model.provider_icon_slug}
                  providerIconUrl={model.provider_icon_url}
                  size={32}
                  showTooltip={false}
                />
              </div>
              <div className="flex-1 min-w-0">
                <DialogTitle className="text-2xl mb-2">{removeProviderPrefix(model.name, model.provider)}</DialogTitle>
                <DialogDescription className="text-sm mb-2">
                  <code className="bg-secondary px-2 py-1 rounded">
                    {model.model_id}
                  </code>
                </DialogDescription>
                <div className="flex items-center gap-2 flex-wrap">
                  {isSelected && (
                    <Badge variant="outline" className="text-xs">
                      <Check className="h-3 w-3 mr-1" />
                      Currently Selected
                    </Badge>
                  )}
                  <Badge
                    variant={model.is_available ? 'default' : 'secondary'}
                    className={cn(
                      'text-xs',
                      model.is_available
                        ? 'bg-green-500/20 text-green-700 dark:text-green-400'
                        : 'bg-gray-500/20 text-gray-700 dark:text-gray-400'
                    )}
                  >
                    {model.is_available ? (
                      <>
                        <Check className="h-3 w-3 mr-1" />
                        Available
                      </>
                    ) : (
                      <>
                        <X className="h-3 w-3 mr-1" />
                        Unavailable
                      </>
                    )}
                  </Badge>
                </div>
              </div>
            </div>
          </DialogHeader>
        </div>

        {/* Content */}
        <ScrollArea className="flex-1 overflow-y-auto">
          <div className="space-y-6 px-6 py-4 pb-8">
            {/* Provider */}
            <div>
              <h3 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider mb-3">
                Provider
              </h3>
              <Badge variant="outline" className="text-base px-3 py-1 flex items-center gap-2 w-fit">
                <ProviderIcon
                  provider={model.provider}
                  providerIconSlug={model.provider_icon_slug}
                  providerIconUrl={model.provider_icon_url}
                  size={16}
                  showTooltip={false}
                />
                {model.provider}
              </Badge>
            </div>

            <Separator />

            {/* Description */}
            {model.description && (
              <>
                <div>
                  <h3 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider mb-3">
                    Description
                  </h3>
                  <Markdown className="text-sm">{model.description}</Markdown>
                </div>
                <Separator />
              </>
            )}

            {/* Pricing */}
            <div>
              <h3 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider mb-3">
                Pricing
              </h3>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="p-4 rounded-lg border border-border bg-secondary/30">
                  <div className="flex items-center gap-2 mb-2">
                    <span className="text-sm font-medium text-muted-foreground">
                      Prompt Tokens
                    </span>
                  </div>
                  <div className="text-2xl font-bold text-foreground">
                    {pricingUtils.formatCost(model.cost_per_1m_prompt)}
                  </div>
                  <div className="text-xs text-muted-foreground mt-1">{pricingUtils.getUnitLabelLong()}</div>
                </div>

                <div className="p-4 rounded-lg border border-border bg-secondary/30">
                  <div className="flex items-center gap-2 mb-2">
                    <span className="text-sm font-medium text-muted-foreground">
                      Completion Tokens
                    </span>
                  </div>
                  <div className="text-2xl font-bold text-foreground">
                    {pricingUtils.formatCost(model.cost_per_1m_completion)}
                  </div>
                  <div className="text-xs text-muted-foreground mt-1">{pricingUtils.getUnitLabelLong()}</div>
                </div>
              </div>
            </div>

            {/* Performance Stats */}
            {(model.latency_p50 != null || model.throughput_p50 != null) && (
              <>
                <Separator />
                <div>
                  <h3 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider mb-3">
                    Performance
                  </h3>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {model.latency_p50 != null && (
                      <div className="p-4 rounded-lg border border-border bg-secondary/30">
                        <div className="flex items-center gap-2 mb-2">
                          <Clock className="h-4 w-4 text-muted-foreground" />
                          <span className="text-sm font-medium text-muted-foreground">
                            Latency (Time to First Token)
                          </span>
                        </div>
                        <div className="text-2xl font-bold text-foreground">
                          {model.latency_p50.toLocaleString()} ms
                        </div>
                        <div className="text-xs text-muted-foreground mt-1">
                          p50 median{model.latency_p90 != null && ` • p90: ${model.latency_p90.toLocaleString()} ms`}
                        </div>
                      </div>
                    )}

                    {model.throughput_p50 != null && (
                      <div className="p-4 rounded-lg border border-border bg-secondary/30">
                        <div className="flex items-center gap-2 mb-2">
                          <Zap className="h-4 w-4 text-muted-foreground" />
                          <span className="text-sm font-medium text-muted-foreground">
                            Throughput
                          </span>
                        </div>
                        <div className="text-2xl font-bold text-foreground">
                          {model.throughput_p50.toFixed(1)} tok/s
                        </div>
                        <div className="text-xs text-muted-foreground mt-1">
                          p50 median{model.throughput_p90 != null && ` • p90: ${model.throughput_p90.toFixed(1)} tok/s`}
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              </>
            )}

            <Separator />

            {/* Capabilities */}
            <div>
              <h3 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider mb-3">
                Capabilities
              </h3>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                <div
                  className={cn(
                    'p-4 rounded-lg border',
                    model.supports_functions
                      ? 'border-accent-brand/30 bg-accent-brand/5'
                      : 'border-border bg-secondary/30'
                  )}
                >
                  <div className="flex items-center gap-2 mb-1">
                    <Code
                      className={cn(
                        'h-4 w-4',
                        model.supports_functions ? 'text-accent-brand' : 'text-muted-foreground'
                      )}
                    />
                    <span className="text-sm font-medium">Function Calling</span>
                  </div>
                  <div className="text-xs text-muted-foreground">
                    {model.supports_functions ? 'Tool calling support' : 'Not supported'}
                  </div>
                </div>

                <div
                  className={cn(
                    'p-4 rounded-lg border',
                    model.supports_structured_outputs
                      ? 'border-accent-brand/30 bg-accent-brand/5'
                      : 'border-border bg-secondary/30'
                  )}
                >
                  <div className="flex items-center gap-2 mb-1">
                    <Braces
                      className={cn(
                        'h-4 w-4',
                        model.supports_structured_outputs ? 'text-accent-brand' : 'text-muted-foreground'
                      )}
                    />
                    <span className="text-sm font-medium">Structured Outputs</span>
                  </div>
                  <div className="text-xs text-muted-foreground">
                    {model.supports_structured_outputs ? 'JSON schema validation' : 'Not supported'}
                  </div>
                </div>

                <div
                  className={cn(
                    'p-4 rounded-lg border',
                    model.supports_reasoning
                      ? 'border-accent-brand/30 bg-accent-brand/5'
                      : 'border-border bg-secondary/30'
                  )}
                >
                  <div className="flex items-center gap-2 mb-1">
                    <Brain
                      className={cn(
                        'h-4 w-4',
                        model.supports_reasoning ? 'text-accent-brand' : 'text-muted-foreground'
                      )}
                    />
                    <span className="text-sm font-medium">Reasoning</span>
                  </div>
                  <div className="text-xs text-muted-foreground">
                    {model.supports_reasoning ? 'Thinking tokens support' : 'Not supported'}
                  </div>
                </div>

                <div
                  className={cn(
                    'p-4 rounded-lg border',
                    model.supports_prompt_caching
                      ? 'border-accent-brand/30 bg-accent-brand/5'
                      : 'border-border bg-secondary/30'
                  )}
                >
                  <div className="flex items-center gap-2 mb-1">
                    <Database
                      className={cn(
                        'h-4 w-4',
                        model.supports_prompt_caching ? 'text-accent-brand' : 'text-muted-foreground'
                      )}
                    />
                    <span className="text-sm font-medium">Prompt Caching</span>
                  </div>
                  <div className="text-xs text-muted-foreground">
                    {model.supports_prompt_caching ? 'Faster & cheaper for repeated prompts' : 'Not supported'}
                  </div>
                </div>

                <div
                  className={cn(
                    'p-4 rounded-lg border',
                    model.supports_stream_cancellation
                      ? 'border-accent-brand/30 bg-accent-brand/5'
                      : 'border-border bg-secondary/30'
                  )}
                >
                  <div className="flex items-center gap-2 mb-1">
                    <Ban
                      className={cn(
                        'h-4 w-4',
                        model.supports_stream_cancellation ? 'text-accent-brand' : 'text-muted-foreground'
                      )}
                    />
                    <span className="text-sm font-medium">Stream Cancellation</span>
                  </div>
                  <div className="text-xs text-muted-foreground">
                    {model.supports_stream_cancellation ? 'Cancel streaming responses' : 'Not supported'}
                  </div>
                </div>

                <div className="p-4 rounded-lg border border-border bg-secondary/30">
                  <div className="flex items-center gap-2 mb-1">
                    <Info className="h-4 w-4 text-muted-foreground" />
                    <span className="text-sm font-medium">Context Length</span>
                  </div>
                  <div className="text-xs text-muted-foreground">
                    Max {model.max_tokens.toLocaleString()} tokens
                  </div>
                </div>
              </div>
            </div>

            {/* Architecture & Modalities */}
            {(model.modality || (model.input_modalities && model.input_modalities.length > 0) || model.tokenizer || model.max_completion_tokens) && (
              <>
                <Separator />
                <div>
                  <h3 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider mb-3">
                    Architecture
                  </h3>
                  <div className="space-y-3">
                    {/* Modality */}
                    {model.modality && (
                      <div className="p-4 rounded-lg border border-border bg-secondary/30">
                        <div className="flex items-center gap-2 mb-2">
                          <Info className="h-4 w-4 text-muted-foreground" />
                          <span className="text-sm font-medium">Modality</span>
                        </div>
                        <div className="text-sm">
                          <code className="bg-background px-2 py-1 rounded">{model.modality}</code>
                        </div>
                      </div>
                    )}

                    {/* Input/Output Modalities */}
                    {model.input_modalities && model.input_modalities.length > 0 && (
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                        <div className="p-4 rounded-lg border border-border bg-secondary/30">
                          <div className="flex items-center gap-2 mb-2">
                            <Info className="h-4 w-4 text-muted-foreground" />
                            <span className="text-sm font-medium">Input Modalities</span>
                          </div>
                          <div className="flex flex-wrap gap-2">
                            {model.input_modalities.includes('text') && (
                              <Badge variant="outline" className="text-xs">
                                <FileText className="h-3 w-3 mr-1" />
                                Text
                              </Badge>
                            )}
                            {model.input_modalities.includes('image') && (
                              <Badge variant="outline" className="text-xs">
                                <Camera className="h-3 w-3 mr-1" />
                                Image
                              </Badge>
                            )}
                            {model.input_modalities.includes('audio') && (
                              <Badge variant="outline" className="text-xs">
                                <Mic className="h-3 w-3 mr-1" />
                                Audio
                              </Badge>
                            )}
                            {model.input_modalities.includes('file') && (
                              <Badge variant="outline" className="text-xs">
                                <FileText className="h-3 w-3 mr-1" />
                                File
                              </Badge>
                            )}
                          </div>
                        </div>

                        {model.output_modalities && model.output_modalities.length > 0 && (
                          <div className="p-4 rounded-lg border border-border bg-secondary/30">
                            <div className="flex items-center gap-2 mb-2">
                              <Info className="h-4 w-4 text-muted-foreground" />
                              <span className="text-sm font-medium">Output Modalities</span>
                            </div>
                            <div className="flex flex-wrap gap-2">
                              {model.output_modalities.includes('text') && (
                                <Badge variant="outline" className="text-xs">
                                  <FileText className="h-3 w-3 mr-1" />
                                  Text
                                </Badge>
                              )}
                              {model.output_modalities.includes('image') && (
                                <Badge variant="outline" className="text-xs">
                                  <Camera className="h-3 w-3 mr-1" />
                                  Image
                                </Badge>
                              )}
                            </div>
                          </div>
                        )}
                      </div>
                    )}

                    {/* Tokenizer & Limits */}
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                      {model.tokenizer && (
                        <div className="p-4 rounded-lg border border-border bg-secondary/30">
                          <div className="flex items-center gap-2 mb-1">
                            <Code className="h-4 w-4 text-muted-foreground" />
                            <span className="text-sm font-medium">Tokenizer</span>
                          </div>
                          <div className="text-xs text-muted-foreground">
                            {model.tokenizer}
                          </div>
                        </div>
                      )}
                      {model.max_completion_tokens && (
                        <div className="p-4 rounded-lg border border-border bg-secondary/30">
                          <div className="flex items-center gap-2 mb-1">
                            <Info className="h-4 w-4 text-muted-foreground" />
                            <span className="text-sm font-medium">Max Completion Tokens</span>
                          </div>
                          <div className="text-xs text-muted-foreground">
                            {model.max_completion_tokens.toLocaleString()} tokens
                          </div>
                        </div>
                      )}
                    </div>

                    {/* Moderation Status */}
                    <div className="p-4 rounded-lg border border-border bg-secondary/30">
                      <div className="flex items-center gap-2 mb-1">
                        <Info className="h-4 w-4 text-muted-foreground" />
                        <span className="text-sm font-medium">Content Moderation</span>
                      </div>
                      <div className="text-xs text-muted-foreground">
                        {model.is_moderated ? 'Moderated by provider' : 'No automatic moderation'}
                      </div>
                    </div>
                  </div>
                </div>
              </>
            )}

            {/* Tags */}
            {model.tags && model.tags.length > 0 && (
              <>
                <Separator />
                <div>
                  <h3 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider mb-3">
                    Tags
                  </h3>
                  <div className="flex flex-wrap gap-2">
                    {model.tags.map((tag) => (
                      <Badge key={tag} variant="outline" className="text-xs">
                        {tag}
                      </Badge>
                    ))}
                  </div>
                </div>
              </>
            )}

            {/* Metadata */}
            <Separator />
            <div>
              <h3 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider mb-3">
                Metadata
              </h3>
              <div className="text-xs text-muted-foreground space-y-1">
                <div>
                  Last updated: {new Date(model.fetched_at).toLocaleString()}
                </div>
              </div>
            </div>
          </div>
        </ScrollArea>

        {/* Footer */}
        <div className="flex-shrink-0 bg-background border-t border-border p-6 pt-4 rounded-b-lg">
          <DialogFooter className="flex-row justify-between sm:justify-between">
            <Button variant="outline" onClick={onClose}>
              Close
            </Button>
            {onSelectModel && (
              <Button
                onClick={handleSelect}
                disabled={!model.is_available}
                className="bg-gradient-to-r from-accent-brand to-accent-brand/80 hover:shadow-glow-brand transition-all text-white"
              >
                <Check className="h-4 w-4 mr-2" />
                {isSelected ? 'Selected' : 'Select Model'}
              </Button>
            )}
          </DialogFooter>
        </div>
      </DialogContent>
    </Dialog>
  )
}
