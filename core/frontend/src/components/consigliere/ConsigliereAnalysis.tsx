/**
 * ConsigliereAnalysis Component
 *
 * Displays AI-powered conversation analysis and model recommendations.
 * Designed with clean flex architecture for proper centering and scrolling.
 */

import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { ScrollArea } from '@/components/ui/scroll-area'
import {
  Sparkles,
  Loader2,
  Check,
  Circle,
  X,
  RotateCw,
  Star,
  ArrowDown,
  ArrowUp,
  Info,
  AlertCircle,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import type {
  ConversationAnalysis,
  RecommendedModelFromConversation,
  ModelRecommendation,
  AnalysisStep,
  AnalysisStepStatus,
  SerializedAttachmentMeta,
} from '@/api/consigliere'
import type { ModelCatalogEntry, ModelFavorite } from '@/types/models'
import type { ChatGroup, Message } from '@/components/models/types'
import useModelStore from '@/store/modelStore'
import { Image as ImageIcon, FileText } from 'lucide-react'
import { ModelIcon } from '@/components/models/ModelIcon'
import { removeProviderPrefix } from '@/lib/model-utils'
import { pricingUtils } from '@/lib/pricing-utils'
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip'

// Helper to parse and format cost savings
const formatCostSavings = (savings: string) => {
  // Handle special cases for free models
  if (savings === 'BOTH_FREE') {
    return {
      text: 'Both free',
      color: 'text-green-600',
      icon: null,
    }
  }

  if (savings === 'BASELINE_FREE') {
    return {
      text: 'Paid alternative (recommended is free)',
      color: 'text-orange-600',
      icon: AlertCircle,
    }
  }

  // Parse percentage (e.g., "+30%" -> 30, "-20%" -> -20)
  const value = parseFloat(savings.replace('%', ''))

  if (value > 0) {
    return {
      text: `${Math.abs(value)}% savings`,
      color: 'text-green-600',
      icon: ArrowDown,
    }
  } else if (value < 0) {
    return {
      text: `${Math.abs(value)}% more expensive`,
      color: 'text-red-600',
      icon: ArrowUp,
    }
  } else {
    return {
      text: 'Same cost',
      color: 'text-muted-foreground',
      icon: null,
    }
  }
}

interface ConsigliereAnalysisProps {
  analysis: ConversationAnalysis | null
  recommendedModel: RecommendedModelFromConversation | null
  alternativeModels: ModelRecommendation[]
  needsAnalysis: boolean
  isGeneratingAnalysis: boolean
  analysisSteps: Record<AnalysisStep, AnalysisStepStatus>
  currentAnalysisStep: AnalysisStep | null
  analysisStepMessage: string
  currentModel: ModelCatalogEntry | null
  favorites: ModelFavorite[]
  chatGroup?: ChatGroup
  onGenerateAnalysis: () => void
  onRegenerateAnalysis: () => void
  onCancelAnalysis: () => void
  onOpenModelDetails: (rec: ModelRecommendation) => void
  onToggleFavorite: (rec: ModelRecommendation, e: React.MouseEvent) => void
}

export function ConsigliereAnalysis({
  analysis,
  recommendedModel,
  alternativeModels,
  needsAnalysis,
  isGeneratingAnalysis,
  analysisSteps,
  currentAnalysisStep,
  analysisStepMessage,
  currentModel,
  favorites,
  chatGroup,
  onGenerateAnalysis,
  onRegenerateAnalysis,
  onCancelAnalysis,
  onOpenModelDetails,
  onToggleFavorite,
}: ConsigliereAnalysisProps) {
  // Step labels for progress display
  const stepLabels: Record<string, string> = {
    preparing_context: 'Building conversation context',
    fetching_models: 'Fetching available models',
    calling_ai: 'Generating AI analysis',
    parsing_response: 'Parsing AI response',
    calculating_costs: 'Calculating cost tradeoffs',
    saving: 'Finalizing analysis',
  }

  // Convert recommendation to ModelCatalogEntry for details modal
  const convertToModelCatalogEntry = (
    rec: ModelRecommendation
  ): ModelCatalogEntry => {
    return {
      id: rec.id,
      model_id: rec.model_id,
      name: rec.model_name,
      provider: rec.provider,
      cost_per_1m_prompt: rec.cost_per_1m_prompt || 0,
      cost_per_1m_completion: rec.cost_per_1m_completion || 0,
      max_tokens: rec.max_tokens || 0,
      supports_streaming: rec.supports_streaming || false,
      supports_functions: rec.supports_functions || false,
      supports_structured_outputs: false,
      supports_reasoning: false,
      supports_prompt_caching: false,
      supports_stream_cancellation: false,
      modality: null,
      input_modalities: [],
      output_modalities: [],
      tokenizer: null,
      max_completion_tokens: null,
      is_moderated: false,
      default_parameters: {},
      description: rec.description || '',
      tags: rec.tags || [],
      is_available: rec.is_available || false,
      fetched_at: new Date().toISOString(),
      model_icon_slug: rec.model_icon_slug,
      model_icon_url: rec.model_icon_url,
      provider_icon_slug: rec.provider_icon_slug,
      provider_icon_url: rec.provider_icon_url,
    }
  }

  // Resolve model details from store (input_modalities capabilities)
  const modelStore = useModelStore()
  const resolveModelDetails = (modelId?: string): ModelCatalogEntry | null => {
    if (!modelId) return null
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
    return found || null
  }

  // Compute attachment summary from chatGroup (if provided)
  const attachmentSummary = (() => {
    const summary = { images: 0, pdfs: 0, files: 0 }
    if (!chatGroup) return summary
    for (const chat of chatGroup.chats || []) {
      for (const msg of chat.messages || []) {
        // Persisted history messages carry this backend-added field; the
        // `Message` type (shared with live, in-flight messages) doesn't model it.
        const atts = (msg as Message & { attachments_meta?: SerializedAttachmentMeta[] }).attachments_meta || []
        for (const a of atts) {
          if (a.type === 'image') summary.images += 1
          else if (a.type === 'file') {
            if (a.is_pdf) summary.pdfs += 1
            else summary.files += 1
          }
        }
      }
    }
    return summary
  })()

  return (
    <div className="flex flex-col flex-1 min-h-0">
      {/* Generate Analysis Button - Centered */}
      {needsAnalysis && !isGeneratingAnalysis && (
        <div className="flex-1 flex flex-col items-center px-4 pt-12">
          <div className="bg-muted/50 border border-dashed rounded-lg p-8 text-center space-y-4 max-w-md">
            <div className="flex flex-col items-center gap-3">
              <Sparkles className="h-12 w-12 text-primary" />
              <h3 className="font-semibold text-lg">AI-Powered Analysis</h3>
              <p className="text-sm text-muted-foreground">
                Use your selected model to analyze this conversation and
                generate personalized insights and model recommendations.
              </p>
            </div>
            <Button
              onClick={onGenerateAnalysis}
              disabled={!currentModel}
              size="lg"
            >
              <Sparkles className="h-4 w-4 mr-2" />
              Generate Analysis
            </Button>
          </div>
        </div>
      )}

      {/* Generating State with Progress Steps */}
      {isGeneratingAnalysis && (
        <div className="flex-1 flex flex-col items-center px-4 pt-12">
          <div className="w-full max-w-2xl bg-muted/30 border rounded-lg p-6 space-y-4">
            <div className="flex items-center gap-2 mb-4">
              <Loader2 className="h-5 w-5 animate-spin text-primary" />
              <h3 className="font-semibold">Generating AI-powered analysis...</h3>
            </div>
            <div className="space-y-3">
              {Object.entries(analysisSteps).map(([step, status]) => {
                const isActive = currentAnalysisStep === step
                const isCompleted = status === 'completed'
                const isInProgress = status === 'in_progress'
                const isPending = status === 'pending'
                const isError = status === 'error'

                return (
                  <div
                    key={step}
                    className={cn(
                      'flex items-center gap-3 transition-all',
                      isActive && 'scale-105'
                    )}
                  >
                    {/* Step Icon */}
                    <div
                      className={cn(
                        'flex-shrink-0 w-6 h-6 rounded-full flex items-center justify-center',
                        isCompleted && 'bg-primary text-primary-foreground',
                        isInProgress && 'bg-primary/20 border-2 border-primary',
                        isPending && 'bg-muted border-2 border-muted-foreground/20',
                        isError && 'bg-destructive text-destructive-foreground'
                      )}
                    >
                      {isCompleted && <Check className="h-4 w-4" />}
                      {isInProgress && (
                        <Loader2 className="h-3 w-3 animate-spin text-primary" />
                      )}
                      {isPending && (
                        <Circle className="h-3 w-3 text-muted-foreground/40" />
                      )}
                      {isError && <X className="h-4 w-4" />}
                    </div>

                    {/* Step Label */}
                    <div className="flex-1 min-w-0">
                      <p
                        className={cn(
                          'text-sm font-medium',
                          isCompleted && 'text-foreground',
                          isInProgress && 'text-foreground font-semibold',
                          isPending && 'text-muted-foreground',
                          isError && 'text-destructive'
                        )}
                      >
                        {stepLabels[step] || step}
                      </p>
                      {isActive && analysisStepMessage && (
                        <p className="text-xs text-muted-foreground mt-0.5">
                          {analysisStepMessage}
                        </p>
                      )}
                    </div>
                  </div>
                )
              })}
            </div>
            <p className="text-xs text-muted-foreground text-center mt-4">
              This may take 60-120 seconds depending on conversation size
            </p>
            <div className="flex justify-center mt-4">
              <Button
                variant="outline"
                size="sm"
                onClick={onCancelAnalysis}
                className="text-destructive hover:text-destructive hover:bg-destructive/10"
              >
                <X className="h-4 w-4 mr-2" />
                Cancel Analysis
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Analysis Results */}
      {analysis && !needsAnalysis && !isGeneratingAnalysis && (
        <ScrollArea className="flex-1 min-h-0 pr-4">
          <div className="space-y-6 px-4 py-4">
            {/* Regenerate Button */}
            <div className="flex items-center justify-between pb-3 border-b">
              <h2 className="text-base font-semibold">AI Analysis Results</h2>
              <Button
                variant="outline"
                size="sm"
                onClick={onRegenerateAnalysis}
                disabled={!currentModel || isGeneratingAnalysis}
              >
                <RotateCw
                  className={cn(
                    'h-4 w-4 mr-2',
                    isGeneratingAnalysis && 'animate-spin'
                  )}
                />
                <span className="hidden sm:inline">Regenerate Analysis</span>
              </Button>
          </div>

          {/* Summary */}
          <div>
            <h3 className="text-sm font-semibold mb-2">
              Conversation Summary
            </h3>
            <div className="grid grid-cols-2 gap-4 text-sm">
              <div>
                <span className="text-muted-foreground">Type:</span>{' '}
                <span className="font-medium">
                  {analysis.conversation_type.replace('_', ' ')}
                </span>
              </div>
              <div>
                <span className="text-muted-foreground">Messages:</span>{' '}
                <span className="font-medium">{analysis.total_messages}</span>
              </div>
              <div>
                <span className="text-muted-foreground">Total Cost:</span>{' '}
                <span className="font-medium">
                  ${analysis.total_cost.toFixed(2)}
                </span>
              </div>
              <div>
                <span className="text-muted-foreground">Avg Latency:</span>{' '}
                <span className="font-medium">
                  {analysis.avg_latency?.toFixed(0)}ms
                </span>
              </div>
              {(attachmentSummary.images || attachmentSummary.pdfs || attachmentSummary.files) && (
                <div className="col-span-2 flex flex-wrap gap-2 mt-1">
                  {attachmentSummary.images > 0 && (
                    <Badge variant="outline" className="text-xs flex items-center gap-1">
                      <ImageIcon className="h-3 w-3" /> {attachmentSummary.images} image{attachmentSummary.images !== 1 ? 's' : ''}
                    </Badge>
                  )}
                  {attachmentSummary.pdfs > 0 && (
                    <Badge variant="outline" className="text-xs flex items-center gap-1">
                      <FileText className="h-3 w-3" /> {attachmentSummary.pdfs} PDF{attachmentSummary.pdfs !== 1 ? 's' : ''}
                    </Badge>
                  )}
                  {attachmentSummary.files > 0 && (
                    <Badge variant="outline" className="text-xs flex items-center gap-1">
                      <FileText className="h-3 w-3" /> {attachmentSummary.files} file{attachmentSummary.files !== 1 ? 's' : ''}
                    </Badge>
                  )}
                </div>
              )}
            </div>
          </div>

            {/* Detected Needs */}
            {analysis.detected_needs &&
              Object.keys(analysis.detected_needs).length > 0 && (
                <div>
                  <h3 className="text-sm font-semibold mb-2">Detected Needs</h3>
                  <div className="grid grid-cols-2 gap-2 text-sm">
                    {analysis.detected_needs.creativity && (
                      <div className="border rounded-md px-3 py-2">
                        <p className="font-medium text-foreground">Creativity</p>
                        <p className="text-xs text-muted-foreground">
                          {analysis.detected_needs.creativity}
                        </p>
                      </div>
                    )}
                    {analysis.detected_needs.precision && (
                      <div className="border rounded-md px-3 py-2">
                        <p className="font-medium text-foreground">Precision</p>
                        <p className="text-xs text-muted-foreground">
                          {analysis.detected_needs.precision}
                        </p>
                      </div>
                    )}
                    {analysis.detected_needs.speed && (
                      <div className="border rounded-md px-3 py-2">
                        <p className="font-medium text-foreground">Speed</p>
                        <p className="text-xs text-muted-foreground">
                          {analysis.detected_needs.speed}
                        </p>
                      </div>
                    )}
                    {analysis.detected_needs.cost_efficiency && (
                      <div className="border rounded-md px-3 py-2">
                        <p className="font-medium text-foreground">
                          Cost Efficiency
                        </p>
                        <p className="text-xs text-muted-foreground">
                          {analysis.detected_needs.cost_efficiency}
                        </p>
                      </div>
                    )}
                  </div>
                </div>
              )}

            {/* Insights */}
            {analysis.insights && analysis.insights.length > 0 && (
              <div>
                <h3 className="text-sm font-semibold mb-2">Key Insights</h3>
                <ul className="space-y-1 text-sm">
                  {analysis.insights.map((insight, idx) => (
                    <li key={idx} className="flex items-start gap-2">
                      <span className="text-primary">•</span>
                      <span>{insight}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {/* Recommended Model (from conversation) */}
            {recommendedModel && (
              <div>
                <h3 className="text-sm font-semibold mb-3">
                  Recommended Model
                </h3>
                <div
                  className="border-2 border-primary rounded-lg p-4 space-y-3 cursor-pointer hover:bg-primary/10 hover:shadow-md transition-all bg-primary/5"
                  onClick={() => {
                    const rec: ModelRecommendation = {
                      ...recommendedModel,
                      id: recommendedModel.model_id,
                      model_name: recommendedModel.model_name || '',
                      rank: 1,
                      reasoning: recommendedModel.reasoning || '',
                      tradeoffs: {},
                    }
                    onOpenModelDetails(rec)
                  }}
                >
                  <div className="flex items-center gap-2">
                    <Badge className="bg-primary text-primary-foreground">
                      Best from conversation
                    </Badge>
                    <ModelIcon
                      modelName={recommendedModel.model_name}
                      modelId={recommendedModel.model_id}
                      provider={recommendedModel.provider}
                      modelIconSlug={recommendedModel.model_icon_slug}
                      modelIconUrl={recommendedModel.model_icon_url}
                      providerIconSlug={recommendedModel.provider_icon_slug}
                      providerIconUrl={recommendedModel.provider_icon_url}
                      size={24}
                      showTooltip={false}
                    />
                    <span className="font-semibold text-lg">
                      {removeProviderPrefix(
                        recommendedModel.model_name,
                        recommendedModel.provider
                      )}
                    </span>
                    <Badge variant="secondary">
                      {recommendedModel.provider}
                    </Badge>
                    {(() => {
                      const details = resolveModelDetails(recommendedModel.model_id)
                      const supportsVision = details?.input_modalities?.includes('image')
                      const supportsPDF = details?.input_modalities?.includes('file')
                      return (
                        <>
                          {supportsVision && (
                            <Badge variant="outline" className="text-[10px]">Vision</Badge>
                          )}
                          {supportsPDF && (
                            <Badge variant="outline" className="text-[10px]">PDF</Badge>
                          )}
                        </>
                      )
                    })()}
                  </div>
                  <p className="text-sm text-muted-foreground">
                    {recommendedModel.reasoning}
                  </p>
                  <div className="flex gap-2 flex-wrap text-xs">
                    <Badge variant="outline" className="text-xs">
                      Prompt:{' '}
                      {pricingUtils.formatCostWithUnit(
                        recommendedModel.cost_per_1m_prompt
                      )}
                    </Badge>
                    <Badge variant="outline" className="text-xs">
                      Completion:{' '}
                      {pricingUtils.formatCostWithUnit(
                        recommendedModel.cost_per_1m_completion
                      )}
                    </Badge>
                    <Badge variant="outline" className="text-xs">
                      Max:{' '}
                      {recommendedModel.max_tokens?.toLocaleString() || 'N/A'}{' '}
                      tokens
                    </Badge>
                  </div>
                  {recommendedModel.metrics && (
                    <div className="flex gap-4 text-xs text-muted-foreground">
                      <span>
                        Messages: {recommendedModel.metrics.total_messages}
                      </span>
                      <span>
                        Avg. Cost: $
                        {recommendedModel.metrics.avg_cost.toFixed(2)}
                      </span>
                      <span>
                        Avg. Latency:{' '}
                        {recommendedModel.metrics.avg_latency.toFixed(0)}ms
                      </span>
                    </div>
                  )}
                  {(() => {
                    const details = resolveModelDetails(recommendedModel.model_id)
                    const supportsVision = details?.input_modalities?.includes('image')
                    const supportsPDF = details?.input_modalities?.includes('file')
                    const showVisionNote = attachmentSummary.images > 0 && !supportsVision
                    const showPdfNote = attachmentSummary.pdfs > 0 && !supportsPDF
                    if (!showVisionNote && !showPdfNote) return null
                    return (
                      <div className="mt-2 text-xs text-muted-foreground">
                        {showVisionNote && (
                          <p>Note: Conversation includes images, but this model may not process image inputs.</p>
                        )}
                        {showPdfNote && (
                          <p>Note: Conversation includes PDFs, but this model may not process file inputs.</p>
                        )}
                      </div>
                    )
                  })()}
                </div>
              </div>
            )}

            {/* Alternative Models */}
            {alternativeModels && alternativeModels.length > 0 && (
              <div>
                <h3 className="text-sm font-semibold mb-3">
                  Alternative Models
                </h3>
                <div className="space-y-3">
                  {alternativeModels.map((rec) => {
                    const isFavorite = favorites.some(
                      (f) => f.model_id === rec.model_id
                    )
                    const details = resolveModelDetails(rec.model_id)
                    const supportsVision = details?.input_modalities?.includes('image')
                    const supportsPDF = details?.input_modalities?.includes('file')

                    return (
                      <div
                        key={rec.id}
                        className="border rounded-lg p-3 space-y-2 cursor-pointer hover:bg-muted/30 hover:border-primary/50 hover:shadow-sm transition-all"
                        onClick={() => onOpenModelDetails(rec)}
                      >
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-2">
                            <Badge variant="outline">#{rec.rank}</Badge>
                            <ModelIcon
                              modelName={rec.model_name}
                              modelId={rec.model_id}
                              provider={rec.provider}
                              modelIconSlug={rec.model_icon_slug}
                              modelIconUrl={rec.model_icon_url}
                              providerIconSlug={rec.provider_icon_slug}
                              providerIconUrl={rec.provider_icon_url}
                              size={20}
                              showTooltip={false}
                            />
                            <span className="font-medium">
                              {removeProviderPrefix(
                                rec.model_name,
                                rec.provider
                              )}
                            </span>
                            <Badge variant="secondary">{rec.provider}</Badge>
                            {supportsVision && (
                              <Badge variant="outline" className="text-[10px]">Vision</Badge>
                            )}
                            {supportsPDF && (
                              <Badge variant="outline" className="text-[10px]">PDF</Badge>
                            )}
                          </div>
                          <div className="flex items-center gap-2">
                            <Button
                              variant="ghost"
                              size="sm"
                              className="h-8 w-8 p-0"
                              onClick={(e) => onToggleFavorite(rec, e)}
                            >
                              <Star
                                className={cn(
                                  'h-4 w-4',
                                  isFavorite && 'fill-yellow-400 text-yellow-400'
                                )}
                              />
                            </Button>
                          </div>
                        </div>
                        <p className="text-sm text-muted-foreground">
                          {rec.reasoning}
                        </p>
                        <div className="flex gap-2 flex-wrap text-xs">
                          <Badge variant="outline" className="text-xs">
                            Prompt:{' '}
                            {pricingUtils.formatCostWithUnit(
                              rec.cost_per_1m_prompt
                            )}
                          </Badge>
                          <Badge variant="outline" className="text-xs">
                            Completion:{' '}
                            {pricingUtils.formatCostWithUnit(
                              rec.cost_per_1m_completion
                            )}
                          </Badge>
                          <Badge variant="outline" className="text-xs">
                            Max: {rec.max_tokens?.toLocaleString() || 'N/A'}{' '}
                            tokens
                          </Badge>
                        </div>
                        {rec.tradeoffs && rec.tradeoffs.cost_savings && (
                          <TooltipProvider>
                            <div className="flex gap-3 text-xs items-center">
                              <div className="flex gap-3 text-muted-foreground">
                                {(() => {
                                  const costInfo = formatCostSavings(
                                    rec.tradeoffs.cost_savings
                                  )
                                  const Icon = costInfo.icon

                                  return (
                                    <span
                                      className={cn(
                                        'flex items-center gap-1',
                                        costInfo.color
                                      )}
                                    >
                                      {Icon && <Icon className="h-3 w-3" />}
                                      {costInfo.text}
                                    </span>
                                  )
                                })()}
                              </div>
                              {rec.tradeoffs.baseline_model_name && (
                                <Tooltip>
                                  <TooltipTrigger asChild>
                                    <Info className="h-3 w-3 text-muted-foreground/60 hover:text-muted-foreground cursor-help flex-shrink-0" />
                                  </TooltipTrigger>
                                  <TooltipContent
                                    side="top"
                                    className="max-w-xs bg-popover border border-border shadow-md"
                                  >
                                    <p className="text-xs text-muted-foreground">
                                      Compared to:
                                    </p>
                                    <p className="font-semibold text-sm text-foreground mt-1">
                                      {rec.tradeoffs.baseline_model_name}
                                    </p>
                                  </TooltipContent>
                                </Tooltip>
                              )}
                            </div>
                          </TooltipProvider>
                        )}
                      </div>
                    )
                  })}
                </div>
              </div>
            )}
          </div>
        </ScrollArea>
      )}
    </div>
  )
}
