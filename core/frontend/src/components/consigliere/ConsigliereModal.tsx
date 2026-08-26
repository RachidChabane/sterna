/**
 * Consigliere AI Advisor Modal
 *
 * Main interface for interacting with the Consigliere AI advisor.
 * Provides conversation analysis, model recommendations, and interactive chat.
 */

import { useState } from 'react'
import { useNavigate } from '@tanstack/react-router'
import { X, Sparkles, Loader2, TrendingUp, MessageSquare } from 'lucide-react'
import { useToast } from '@/hooks/use-toast'
import { getUserFriendlyErrorMessage } from '@/utils/errorMessages'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useConsigliereStore } from '@/store/consigliereStore'
import useModelStore from '@/store/modelStore'
import { ModelDetailsModal } from '@/components/models/ModelDetailsModal'
import type { ModelCatalogEntry } from '@/types/models'
import type { ModelRecommendation } from '@/api/consigliere'
import { ConsigliereEmptyState } from './ConsigliereEmptyState'
import { ConsigliereChat } from './ConsigliereChat'
import { ConsigliereAnalysis } from './ConsigliereAnalysis'
import { ModelControlBar } from './ModelControlBar'
import type { Model } from '@/components/models/types'

export function ConsigliereModal() {
  const {
    isOpen,
    closeConsigliere,
    currentSession,
    messages,
    analysis,
    recommendedModel,
    alternativeModels,
    recommendations, // deprecated - fallback
    isAnalyzing,
    isGeneratingAnalysis,
    isChatting,
    generateAnalysis,
    cancelAnalysis,
    cancelChat,
    sendMessage,
    clearMessages,
    error,
    clearError,
    analysisSteps,
    currentAnalysisStep,
    analysisStepMessage,
    parameters,
    updateParameters,
    getNormalizedMessages,
    chatAbortController,
  } = useConsigliereStore()

  const [isClearingMessages, setIsClearingMessages] = useState(false)
  const [showClearChatDialog, setShowClearChatDialog] = useState(false)
  const { toast } = useToast()
  const navigate = useNavigate()

  const { currentModel, favorites, recentModels, setCurrentModel, addFavorite, removeFavorite } = useModelStore()
  const [selectedModelForDetails, setSelectedModelForDetails] = useState<ModelCatalogEntry | null>(null)
  const [isDetailsModalOpen, setIsDetailsModalOpen] = useState(false)

  const handleSendMessage = async (content: string) => {
    if (!content.trim() || !currentModel) return
    await sendMessage(content, currentModel.model_id, {
      name: currentModel.name,
      provider: currentModel.provider,
      model_icon_slug: currentModel.model_icon_slug,
      model_icon_url: currentModel.model_icon_url,
      provider_icon_slug: currentModel.provider_icon_slug,
      provider_icon_url: currentModel.provider_icon_url,
    })
  }

  const handleRetry = async () => {
    if (!currentModel) return
    await useConsigliereStore.getState().retryLastAndResend(currentModel.model_id, {
      name: currentModel.name,
      provider: currentModel.provider,
      model_icon_slug: currentModel.model_icon_slug,
      model_icon_url: currentModel.model_icon_url,
      provider_icon_slug: currentModel.provider_icon_slug,
      provider_icon_url: currentModel.provider_icon_url,
    })
  }

  const handleSuggestionClick = (suggestion: string) => {
    // Directly send the suggestion message
    handleSendMessage(suggestion)
  }

  const handleClearChat = async () => {
    setShowClearChatDialog(false)
    setIsClearingMessages(true)
    try {
      await clearMessages()
      toast({
        title: 'Conversation cleared',
        description: 'All messages have been deleted successfully',
      })
    } catch (error) {
      console.error('Failed to clear messages:', error)
      toast({
        title: 'Failed to clear conversation',
        description: getUserFriendlyErrorMessage(error),
        variant: 'destructive',
      })
    } finally {
      setIsClearingMessages(false)
    }
  }

  const handleModelChange = (model: ModelCatalogEntry) => {
    setCurrentModel(model)
    toast({
      title: 'Model changed',
      description: `Now using ${model.name}`,
    })
  }

  const handleBrowseModels = () => {
    // Close Consigliere modal
    closeConsigliere()
    // Navigate to models page
    navigate({ to: '/models' })
  }

  // Convert ModelCatalogEntry to Model type for ChatPanel
  const chatPanelModel: Model | null = currentModel ? {
    id: currentModel.id,
    model_id: currentModel.model_id,
    name: currentModel.name,
    provider: currentModel.provider,
    cost_per_1m_prompt: currentModel.cost_per_1m_prompt,
    cost_per_1m_completion: currentModel.cost_per_1m_completion,
    max_tokens: currentModel.max_tokens,
    supports_streaming: currentModel.supports_streaming,
    supports_functions: currentModel.supports_functions,
    supports_structured_outputs: currentModel.supports_structured_outputs,
    supports_reasoning: currentModel.supports_reasoning,
    supports_prompt_caching: currentModel.supports_prompt_caching,
    supports_stream_cancellation: currentModel.supports_stream_cancellation,
    input_modalities: currentModel.input_modalities,
    output_modalities: currentModel.output_modalities,
    is_available: currentModel.is_available,
    model_icon_slug: currentModel.model_icon_slug,
    model_icon_url: currentModel.model_icon_url,
    provider_icon_slug: currentModel.provider_icon_slug,
    provider_icon_url: currentModel.provider_icon_url,
    tags: currentModel.tags,
  } : null

  const handleGenerateAnalysis = async () => {
    if (!currentModel) return
    await generateAnalysis(currentModel.model_id)
  }

  const handleRegenerateAnalysis = async () => {
    if (!currentModel) return
    await generateAnalysis(currentModel.model_id)
  }

  // Convert recommendation to ModelCatalogEntry for the details modal
  const convertToModelCatalogEntry = (rec: ModelRecommendation): ModelCatalogEntry => {
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

  const handleOpenModelDetails = (rec: ModelRecommendation) => {
    const modelEntry = convertToModelCatalogEntry(rec)
    setSelectedModelForDetails(modelEntry)
    setIsDetailsModalOpen(true)
  }

  const handleToggleFavorite = (rec: ModelRecommendation, e: React.MouseEvent) => {
    e.stopPropagation() // Prevent opening details modal
    const isFavorite = favorites.some((f) => f.model_id === rec.model_id)
    if (isFavorite) {
      removeFavorite(rec.model_id)
    } else {
      const modelEntry = convertToModelCatalogEntry(rec)
      addFavorite(rec.model_id, modelEntry)
    }
  }

  // Use new fields with fallback to deprecated field
  const displayRecommendations = alternativeModels.length > 0 ? alternativeModels : recommendations

  // Check if we need to show the "Generate Analysis" button
  const needsAnalysis = !!analysis && (
    !analysis.conversation_type ||
    !analysis.detected_needs ||
    Object.keys(analysis.detected_needs).length === 0 ||
    !displayRecommendations ||
    displayRecommendations.length === 0
  )

  return (
    <>
    <Dialog open={isOpen} onOpenChange={closeConsigliere}>
      <DialogContent className="max-w-4xl h-[85vh] flex flex-col">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Sparkles className="h-5 w-5 text-primary" />
            Consigliere AI Advisor
          </DialogTitle>
          <DialogDescription>
            Get expert recommendations on which models to use based on your conversation
          </DialogDescription>
        </DialogHeader>

        {/* Model Control Bar */}
        <ModelControlBar
          currentModel={currentModel}
          recentModels={recentModels}
          favorites={favorites}
          onModelChange={handleModelChange}
          onBrowseClick={handleBrowseModels}
          onStop={cancelChat}
          canStop={Boolean(chatAbortController)}
          onCopyResponses={() => {
            const text = getNormalizedMessages()
              .filter(m => m.role === 'assistant')
              .map(m => (typeof m.content === 'string' ? m.content : ''))
              .join('\n\n---\n\n')
            navigator.clipboard.writeText(text)
            toast({ title: 'Copied', description: 'All responses copied to clipboard' })
          }}
          onCopyMetadata={() => {
            const metadata = getNormalizedMessages()
              .filter(m => m.role === 'assistant')
              .map(m => ({
                model: m.model,
                model_id: m.model_id,
                provider: m.provider,
                timestamp: m.timestamp,
                cost: m.cost,
                prompt_cost: m.prompt_cost,
                completion_cost: m.completion_cost,
                latency: m.latency,
                tokens: m.tokens,
              }))
            navigator.clipboard.writeText(JSON.stringify(metadata, null, 2))
            toast({ title: 'Copied', description: 'All metadata copied to clipboard' })
          }}
          onExportResponses={() => {
            const text = getNormalizedMessages()
              .filter(m => m.role === 'assistant')
              .map(m => (typeof m.content === 'string' ? m.content : ''))
              .join('\n\n---\n\n')
            const blob = new Blob([text], { type: 'text/plain' })
            const url = URL.createObjectURL(blob)
            const a = document.createElement('a')
            a.href = url
            a.download = `consigliere-chat-${currentModel?.name || 'unknown'}-${Date.now()}.txt`
            a.click()
            URL.revokeObjectURL(url)
            toast({ title: 'Exported', description: 'All responses exported' })
          }}
          onExportMetadata={() => {
            const metadata = getNormalizedMessages()
              .filter(m => m.role === 'assistant')
              .map(m => ({
                model: m.model,
                model_id: m.model_id,
                provider: m.provider,
                timestamp: m.timestamp,
                cost: m.cost,
                prompt_cost: m.prompt_cost,
                completion_cost: m.completion_cost,
                latency: m.latency,
                tokens: m.tokens,
              }))
            const blob = new Blob([JSON.stringify(metadata, null, 2)], { type: 'application/json' })
            const url = URL.createObjectURL(blob)
            const a = document.createElement('a')
            a.href = url
            a.download = `consigliere-chat-metadata-${currentModel?.name || 'unknown'}-${Date.now()}.json`
            a.click()
            URL.revokeObjectURL(url)
            toast({ title: 'Exported', description: 'All metadata exported' })
          }}
          onClearChat={() => setShowClearChatDialog(true)}
          clearDisabled={getNormalizedMessages().length === 0 || isChatting || isClearingMessages}
        />

        {isAnalyzing ? (
          <div className="flex flex-col items-center justify-center py-12 space-y-4">
            <Loader2 className="h-8 w-8 animate-spin text-primary" />
            <p className="text-muted-foreground">Analyzing your conversation...</p>
          </div>
        ) : (
          <Tabs defaultValue="chat" className="flex flex-col flex-1 min-h-0">
            <TabsList className="grid w-full grid-cols-2">
              <TabsTrigger value="chat">
                <MessageSquare className="h-4 w-4 mr-2" />
                Chat
              </TabsTrigger>
              <TabsTrigger value="analysis">
                <TrendingUp className="h-4 w-4 mr-2" />
                Analysis & Recommendations
              </TabsTrigger>
            </TabsList>

            {/* Chat Tab */}
            <TabsContent
              value="chat"
              className="flex-1 flex flex-col min-h-0 data-[state=inactive]:hidden data-[state=inactive]:flex-none"
            >
              <ConsigliereChat
                model={chatPanelModel}
                messages={getNormalizedMessages()}
                isLoading={isChatting}
                onSendMessage={handleSendMessage}
                emptyStateContent={
                  <ConsigliereEmptyState onSuggestionClick={handleSuggestionClick} />
                }
                inputPlaceholder="Ask Consigliere about model recommendations..."
                onClearChat={handleClearChat}
                isClearingChat={isClearingMessages || isChatting}
                onOpenClearDialog={() => setShowClearChatDialog(true)}
                onCancel={cancelChat}
                canCancel={Boolean(chatAbortController)}
                onRetry={handleRetry}
              />
            </TabsContent>

            {/* Analysis Tab */}
            <TabsContent
              value="analysis"
              className="flex-1 flex flex-col min-h-0 data-[state=inactive]:hidden data-[state=inactive]:flex-none"
            >
          <ConsigliereAnalysis
            analysis={analysis}
            recommendedModel={recommendedModel}
            alternativeModels={displayRecommendations}
            needsAnalysis={needsAnalysis}
            isGeneratingAnalysis={isGeneratingAnalysis}
            analysisSteps={analysisSteps}
            currentAnalysisStep={currentAnalysisStep}
            analysisStepMessage={analysisStepMessage}
            currentModel={currentModel}
            favorites={favorites}
            chatGroup={currentSession?.chat_group_data}
            onGenerateAnalysis={handleGenerateAnalysis}
            onRegenerateAnalysis={handleRegenerateAnalysis}
            onCancelAnalysis={cancelAnalysis}
            onOpenModelDetails={handleOpenModelDetails}
            onToggleFavorite={handleToggleFavorite}
          />
            </TabsContent>
          </Tabs>
        )}
      </DialogContent>
    </Dialog>

    {/* Model Details Modal */}
    <ModelDetailsModal
      isOpen={isDetailsModalOpen}
      onClose={() => setIsDetailsModalOpen(false)}
      model={selectedModelForDetails}
    />

    {/* Clear Chat Confirmation Dialog */}
    <Dialog open={showClearChatDialog} onOpenChange={setShowClearChatDialog}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Clear Conversation?</DialogTitle>
          <DialogDescription>
            This will permanently delete all messages in this conversation.
            Your analysis and recommendations will remain intact.
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button variant="outline" onClick={() => setShowClearChatDialog(false)}>
            Cancel
          </Button>
          <Button
            variant="destructive"
            onClick={handleClearChat}
          >
            Clear Messages
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
    </>
  )
}
